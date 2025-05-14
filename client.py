# client.py
import asyncio
import json
import datetime
import websockets
import aioconsole

async def receive_messages(websocket):
    """Menangani pesan yang masuk dari server"""
    try:
        async for message in websocket:
            data = json.loads(message)
            print(f"\n[{data.get('timestamp', '')}] {data['username']}: {data['message']}")
            print("Pesan: ", end="", flush=True)
    except websockets.exceptions.ConnectionClosed:
        print("\nKoneksi ke server terputus.")

async def send_messages(websocket, username):
    """Mengirim pesan ke server"""
    try:
        while True:
            message = await aioconsole.ainput("Pesan: ")
            if message.lower() == 'quit':
                break
                
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            data = {
                "username": username,
                "message": message,
                "timestamp": timestamp
            }
            await websocket.send(json.dumps(data))
    except Exception as e:
        print(f"Error: {e}")

async def main():
    # Meminta username
    username = input("Masukkan username Anda: ")
    print(f"Selamat datang, {username}! Ketik 'quit' untuk keluar.")
    
    # Koneksi ke server WebSocket
    uri = "ws://localhost:8765"
    try:
        async with websockets.connect(uri) as websocket:
            print(f"Terhubung ke {uri}")
            # Jalankan fungsi kirim dan terima pesan secara bersamaan
            await asyncio.gather(
                receive_messages(websocket),
                send_messages(websocket, username)
            )
    except Exception as e:
        print(f"Gagal terhubung ke server: {e}")

if __name__ == "__main__":
    asyncio.run(main())