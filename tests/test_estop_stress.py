import requests
import time
import threading

BASE_URL = "http://localhost:8000/api"
LOCO_ID = "60337"

def flood_speed():
    for i in range(100):
        requests.post(f"{BASE_URL}/loco/{LOCO_ID}/speed/30")

print("Flooding queue...")
flood_thread = threading.Thread(target=flood_speed)
flood_thread.start()

time.sleep(0.5)
t0 = time.time()
requests.post(f"{BASE_URL}/estop")
print(f"E-Stop sent at {t0}. Count the seconds until the physical wheels stop!")