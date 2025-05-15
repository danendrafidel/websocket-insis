import asyncio
import json
import datetime
import websockets
import aioconsole
import logging
import sys
import time
import getpass

# Konfigurasi logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChatClient:
    def __init__(self):
        self.websocket = None
        self.username = None
        self.auth_token = None
        self.uri = "ws://localhost:8765"
        self.is_shutting_down = False
        self.is_authenticated = False

    async def handle_auth_response(self, message):
        """Menangani respons autentikasi dari server"""
        try:
            data = json.loads(message)
            if not isinstance(data, dict) or "type" not in data:
                logger.debug(f"Pesan tidak valid diterima: {message}")
                return False

            if data["type"] == "auth_request":
                # Server meminta username
                username = input(f"{data['message']}: ")
                await self.websocket.send(json.dumps({"username": username}))
                return True
            elif data["type"] == "password_request":
                # Server meminta password
                password = getpass.getpass(f"{data['message']}: ")
                await self.websocket.send(json.dumps({"password": password}))
                return True
            elif data["type"] == "auth_success":
                # Autentikasi berhasil
                self.auth_token = data["token"]
                self.is_authenticated = True
                logger.info(data["message"])
                return True
            elif data["type"] == "server_shutdown":
                # Server akan dimatikan
                logger.warning(f"\n[{data.get('timestamp', '')}] {data['message']}")
                self.is_shutting_down = True
                return True
            elif data["type"] == "server_closed":
                # Server sudah ditutup
                logger.warning(f"\n[{data.get('timestamp', '')}] {data['message']}")
                self.is_shutting_down = True
                return True
            return False
        except json.JSONDecodeError:
            logger.debug(f"Format pesan tidak valid: {message}")
            return False
        except Exception as e:
            logger.debug(f"Error dalam autentikasi: {e}")
            return False

    async def receive_messages(self):
        """Menangani pesan yang masuk dari server"""
        try:
            async for message in self.websocket:
                if isinstance(message, str):
                    # Cek apakah ini pesan autentikasi, shutdown, atau server closed
                    if await self.handle_auth_response(message):
                        if self.is_shutting_down:
                            return False
                        continue
                        
                    try:
                        data = json.loads(message)
                        if not isinstance(data, dict) or "username" not in data or "message" not in data:
                            logger.debug(f"Pesan chat tidak valid: {message}")
                            continue
                        print(f"\n[{data.get('timestamp', '')}] {data['username']}: {data['message']}")
                        print("Pesan: ", end="", flush=True)
                    except json.JSONDecodeError:
                        logger.debug(f"Format pesan tidak valid: {message}")
                        continue
        except websockets.exceptions.ConnectionClosed as e:
            if e.code == 1008 and not self.is_authenticated:
                # Kode 1008 menandakan penolakan autentikasi atau akses di luar jam
                logger.error("\nGagal terhubung: Autentikasi gagal atau server hanya aktif pada jam 08:00-19:59")
            elif not self.is_authenticated:
                logger.error(f"\nKoneksi terputus sebelum autentikasi: {e}")
            else:
                logger.error(f"\nKoneksi terputus: {e}")
            return False
        except Exception as e:
            logger.debug(f"Error saat menerima pesan: {e}")
            return False
        return True

    async def send_messages(self):
        """Mengirim pesan ke server"""
        try:
            while not self.is_shutting_down:
                if not self.is_authenticated:
                    await asyncio.sleep(0.1)
                    continue

                message = await aioconsole.ainput("Pesan: ")
                if message.lower() == 'quit':
                    await self.websocket.close(1000, "Client menutup koneksi")
                    return False
                    
                timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                data = {
                    "token": self.auth_token,
                    "message": message,
                    "timestamp": timestamp
                }
                try:
                    await self.websocket.send(json.dumps(data))
                except websockets.exceptions.ConnectionClosed:
                    logger.error("\nTidak dapat mengirim pesan: koneksi terputus")
                    return False
        except Exception as e:
            logger.debug(f"Error saat mengirim pesan: {e}")
            return False
        return True

    async def connect_with_retry(self, max_retries=5, retry_delay=5):
        """Mencoba koneksi dengan retry"""
        for attempt in range(max_retries):
            try:
                async with websockets.connect(
                    self.uri,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=10
                ) as websocket:
                    self.websocket = websocket
                    logger.info(f"Terhubung ke {self.uri}")
                    
                    # Reset status autentikasi
                    self.is_authenticated = False
                    self.auth_token = None
                    
                    receive_task = asyncio.create_task(self.receive_messages())
                    send_task = asyncio.create_task(self.send_messages())
                    
                    # Tunggu salah satu task selesai
                    done, pending = await asyncio.wait(
                        [receive_task, send_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    
                    # Cancel task yang masih berjalan
                    for task in pending:
                        task.cancel()
                    
                    # Cek hasil task yang selesai
                    for task in done:
                        if not task.result():
                            if attempt < max_retries - 1:
                                logger.info(f"Mencoba koneksi ulang dalam {retry_delay} detik...")
                                await asyncio.sleep(retry_delay)
                            continue
                            
            except websockets.exceptions.ConnectionClosed as e:
                if e.code == 1008:
                    logger.error(f"Gagal terhubung: Autentikasi gagal atau server hanya aktif pada jam 08:00-19:59")
                else:
                    logger.error(f"Koneksi terputus: {e}")
            except websockets.exceptions.WebSocketException as e:
                logger.error(f"Error WebSocket: {e}")
            except Exception as e:
                logger.error(f"Error koneksi: {e}")
                
            if attempt < max_retries - 1:
                logger.info(f"Mencoba koneksi ulang dalam {retry_delay} detik...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error("Gagal terhubung setelah beberapa percobaan")
                return False
        
        return False

async def main():
    client = ChatClient()
    
    try:
        if not await client.connect_with_retry():
            sys.exit(1)
    except KeyboardInterrupt:
        logger.info("\nProgram dihentikan oleh user")
    except Exception as e:
        logger.debug(f"Error tidak terduga: {e}")
    finally:
        logger.info("Program selesai")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nProgram dihentikan oleh user")
    except Exception as e:
        logger.debug(f"Error tidak terduga: {e}")
    finally:
        logger.info("Program selesai")