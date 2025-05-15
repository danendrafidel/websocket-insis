# users.py
import json
import os
from typing import Dict, Optional

class UserManager:
    def __init__(self, users_file: str = "users.json"):
        self.users_file = users_file
        self.users: Dict[str, str] = {}
        self.load_users()

    def load_users(self) -> None:
        """Memuat data pengguna dari file JSON"""
        if os.path.exists(self.users_file):
            try:
                with open(self.users_file, 'r') as f:
                    self.users = json.load(f)
            except json.JSONDecodeError:
                print("Error: File users.json rusak. Membuat file baru.")
                self.users = {}
                self.save_users()
        else:
            # Buat file dengan beberapa pengguna default
            self.users = {
                "adminganteng": "admin123",
                "maulana": "pass123",
                "atha": "pass123"
            }
            self.save_users()

    def save_users(self) -> None:
        """Menyimpan data pengguna ke file JSON"""
        with open(self.users_file, 'w') as f:
            json.dump(self.users, f, indent=4)

    def verify_credentials(self, username: str, password: str) -> bool:
        """Verifikasi kredensial pengguna"""
        return username in self.users and self.users[username] == password

    def add_user(self, username: str, password: str) -> bool:
        """Menambahkan pengguna baru"""
        if username in self.users:
            return False
        self.users[username] = password
        self.save_users()
        return True

    def remove_user(self, username: str) -> bool:
        """Menghapus pengguna"""
        if username not in self.users:
            return False
        del self.users[username]
        self.save_users()
        return True

    def change_password(self, username: str, new_password: str) -> bool:
        """Mengubah password pengguna"""
        if username not in self.users:
            return False
        self.users[username] = new_password
        self.save_users()
        return True

    def get_all_users(self) -> Dict[str, str]:
        """Mendapatkan semua data pengguna"""
        return self.users.copy()

# Buat instance UserManager global
user_manager = UserManager() 