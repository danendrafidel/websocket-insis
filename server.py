# server.py
import asyncio
import json
import websockets

# Menyimpan koneksi klien yang aktif
connected_clients = set()

async def handle_message(websocket):
    """Handler untuk koneksi WebSocket baru"""
    # Daftarkan client baru
    connected_clients.add(websocket)
    try:
        async for message in websocket:
            data = json.loads(message)
            # Format pesan
            broadcast_message = {
                "username": data["username"],
                "message": data["message"],
                "timestamp": data.get("timestamp", "")
            }
            # Broadcast ke semua client yang terhubung
            if connected_clients:
                await asyncio.gather(
                    *[client.send(json.dumps(broadcast_message)) 
                      for client in connected_clients]
                )
    except websockets.exceptions.ConnectionClosed:
        print("Koneksi terputus")
    finally:
        # Hapus client ketika terputus
        connected_clients.remove(websocket)

async def main():
    server = await websockets.serve(
        handle_message,
        "localhost",
        8765
    )
    print("Server chat berjalan di ws://localhost:8765")
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())

# Nambahin Broadcast kalau semisal koneksi servernnya tutup
# Tambahin bisa akses di jam tertentu
