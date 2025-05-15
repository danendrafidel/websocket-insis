import asyncio
import json
import websockets
import time
import logging
import signal
import sys
import secrets
from datetime import datetime, timedelta
from users import user_manager

# Konfigurasi logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Konfigurasi server
MAX_CONNECTIONS = 5
AUTH_TIMEOUT = 3600
TOKEN_EXPIRY = 3600
ALLOWED_HOURS = range(8, 20)  # Server hanya bisa diakses dari jam 08:00 - 19:59

# Menyimpan koneksi klien yang aktif
connected_clients = set()
client_ping_times = {}
auth_tokens = {}
pending_auth = {}

# Konfigurasi heartbeat
HEARTBEAT_INTERVAL = 3600
PING_TIMEOUT = 3600

# Flag untuk graceful shutdown
shutdown_event = asyncio.Event()

def generate_token():
    """Generate token autentikasi"""
    return secrets.token_urlsafe(32)

def is_token_valid(token):
    """Cek apakah token masih valid"""
    if token not in auth_tokens:
        return False
    return datetime.now() < auth_tokens[token]["expiry"]

def is_access_allowed():
    """Cek apakah waktu saat ini berada dalam jam yang diizinkan"""
    current_hour = datetime.now().hour
    return current_hour in ALLOWED_HOURS

async def cleanup_expired_tokens():
    """Membersihkan token yang sudah kadaluarsa"""
    while not shutdown_event.is_set():
        current_time = datetime.now()
        expired_tokens = [
            token for token, data in auth_tokens.items()
            if current_time >= data["expiry"]
        ]
        for token in expired_tokens:
            del auth_tokens[token]
        await asyncio.sleep(60)

async def broadcast_server_shutdown():
    """Broadcast pesan shutdown ke semua client"""
    if connected_clients:
        shutdown_message = {
            "type": "server_shutdown",
            "message": "Server akan dimatikan dalam 5 detik",
            "timestamp": datetime.now().strftime("%H:%M:%S")
        }
        try:
            await asyncio.gather(
                *[client.send(json.dumps(shutdown_message)) 
                  for client in connected_clients],
                return_exceptions=True
            )
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Error saat broadcast shutdown: {e}")

async def broadcast_server_closed():
    """Broadcast pesan ketika server benar-benar ditutup"""
    if connected_clients:
        close_message = {
            "type": "server_closed",
            "message": "Server telah ditutup",
            "timestamp": datetime.now().strftime("%H:%M:%S")
        }
        try:
            await asyncio.gather(
                *[client.send(json.dumps(close_message)) 
                  for client in connected_clients],
                return_exceptions=True
            )
        except Exception as e:
            logger.error(f"Error saat broadcast server closed: {e}")

async def check_heartbeat():
    """Memeriksa koneksi client menggunakan heartbeat"""
    while not shutdown_event.is_set():
        try:
            current_time = time.time()
            disconnected_clients = set()
            
            for client in connected_clients:
                last_ping = client_ping_times.get(client, 0)
                if current_time - last_ping > PING_TIMEOUT:
                    logger.warning(f"Client timeout - tidak ada heartbeat dalam {PING_TIMEOUT} detik")
                    disconnected_clients.add(client)
            
            for client in disconnected_clients:
                connected_clients.remove(client)
                client_ping_times.pop(client, None)
                try:
                    await client.close(1000, "Timeout - tidak ada heartbeat")
                except Exception as e:
                    logger.error(f"Error saat menutup koneksi client: {e}")
            
            await asyncio.sleep(HEARTBEAT_INTERVAL)
        except Exception as e:
            logger.error(f"Error dalam heartbeat checker: {e}")
            await asyncio.sleep(1)

async def handle_authentication(websocket):
    """Menangani proses autentikasi"""
    try:
        # Cek akses berdasarkan jam
        if not is_access_allowed():
            await websocket.close(1008, "Server hanya dapat diakses pada jam 08:00-19:59")
            return None

        auth_request = {
            "type": "auth_request",
            "message": "Silakan masukkan username Anda"
        }
        await websocket.send(json.dumps(auth_request))
        
        response = await websocket.recv()
        data = json.loads(response)
        
        if "username" not in data:
            await websocket.close(1008)
            return None
            
        username = data["username"]
        
        password_request = {
            "type": "password_request",
            "message": "Silakan masukkan password Anda"
        }
        await websocket.send(json.dumps(password_request))
        
        response = await websocket.recv()
        data = json.loads(response)
        
        if "password" not in data:
            await websocket.close(1008)
            return None
            
        password = data["password"]
        
        if not user_manager.verify_credentials(username, password):
            await websocket.close(1008)
            return None
        
        pending_auth[websocket] = {
            "username": username,
            "start_time": datetime.now()
        }
        
        token = generate_token()
        auth_tokens[token] = {
            "username": username,
            "expiry": datetime.now() + timedelta(seconds=TOKEN_EXPIRY)
        }
        
        auth_response = {
            "type": "auth_success",
            "token": token,
            "message": "Autentikasi berhasil"
        }
        await websocket.send(json.dumps(auth_response))
        
        return username
        
    except websockets.exceptions.ConnectionClosed:
        return None
    except Exception as e:
        logger.error(f"Error dalam autentikasi: {e}")
        return None

async def handle_message(websocket):
    """Handler untuk koneksi WebSocket baru"""
    if len(connected_clients) >= MAX_CONNECTIONS:
        await websocket.close(1008, "Server penuh")
        return
        
    username = await handle_authentication(websocket)
    if not username:
        return
        
    connected_clients.add(websocket)
    client_ping_times[websocket] = time.time()
    
    try:
        while not shutdown_event.is_set():
            try:
                pong_waiter = await websocket.ping()
                start_time = time.time()
                
                await pong_waiter
                end_time = time.time()
                
                latency = (end_time - start_time) * 1000
                logger.info(f"Latency untuk {username}: {latency:.2f}ms")
                
                client_ping_times[websocket] = time.time()
                
                await asyncio.sleep(5)
                
            except websockets.exceptions.ConnectionClosed:
                break
                
            async for message in websocket:
                if shutdown_event.is_set():
                    break
                    
                try:
                    data = json.loads(message)
                    
                    if "token" not in data or not is_token_valid(data["token"]):
                        await websocket.close(1008)
                        return
                        
                    broadcast_message = {
                        "username": username,
                        "message": data["message"],
                        "timestamp": data.get("timestamp", "")
                    }
                    if connected_clients:
                        await asyncio.gather(
                            *[client.send(json.dumps(broadcast_message)) 
                              for client in connected_clients]
                        )
                except json.JSONDecodeError:
                    logger.error("Pesan tidak valid: format JSON salah")
                except Exception as e:
                    logger.error(f"Error saat memproses pesan: {e}")
                    
    except websockets.exceptions.ConnectionClosed as e:
        logger.info(f"Koneksi terputus: {e}")
    except Exception as e:
        logger.error(f"Error dalam handle_message: {e}")
    finally:
        connected_clients.remove(websocket)
        client_ping_times.pop(websocket, None)
        pending_auth.pop(websocket, None)

async def shutdown(server):
    """Graceful shutdown server"""
    logger.info("Memulai proses shutdown...")
    shutdown_event.set()
    
    await broadcast_server_shutdown()
    await broadcast_server_closed()  # Tambahan broadcast server closed
    
    if connected_clients:
        await asyncio.gather(
            *[client.close(1000, "Server shutdown") for client in connected_clients],
            return_exceptions=True
        )
    
    server.close()
    await server.wait_closed()
    logger.info("Server berhasil dimatikan")

async def main():
    heartbeat_task = asyncio.create_task(check_heartbeat())
    cleanup_task = asyncio.create_task(cleanup_expired_tokens())
    
    server = await websockets.serve(
        handle_message,
        "localhost",
        8765
    )
    logger.info(f"Server chat berjalan di ws://localhost:8765 (Maksimal {MAX_CONNECTIONS} koneksi)")
    
    try:
        await shutdown_event.wait()
    except KeyboardInterrupt:
        logger.info("Menerima sinyal shutdown")
    finally:
        await shutdown(server)
        heartbeat_task.cancel()
        cleanup_task.cancel()
        try:
            await asyncio.gather(heartbeat_task, cleanup_task, return_exceptions=True)
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Program dihentikan oleh user")
    except Exception as e:
        logger.error(f"Error tidak terduga: {e}")
    finally:
        logger.info("Program selesai")