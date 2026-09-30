import asyncio
import re
import xml.etree.ElementTree as ET
import os

class RocrailAdapter:
    def __init__(self, host="127.0.0.1", port=8051):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
        self.connected = False
        self.state = {"status": "offline", "locomotives": {}, "switches": {}}
        
        # Load the static layout from the file immediately
        self.load_plan()

    def load_plan(self):
        # Look for plan.xml in the root of the exhibit-ui folder
        plan_path = os.path.join(os.path.dirname(__file__), '..', 'plan.xml')
        try:
            tree = ET.parse(plan_path)
            root = tree.getroot()
            
            # Extract all locomotives
            for lc in root.iter('lc'):
                loc_id = lc.get('id')
                if loc_id:
                    self.state["locomotives"][loc_id] = {
                        "speed": lc.get('V', 0), 
                        "direction": "forward"
                    }
                    
            # Extract all switches
            for sw in root.iter('sw'):
                sw_id = sw.get('id')
                if sw_id:
                    self.state["switches"][sw_id] = {
                        "state": sw.get('state', 'unknown')
                    }
                    
            print(f"Loaded {len(self.state['locomotives'])} locomotives and {len(self.state['switches'])} switches from plan.xml!")
        except Exception as e:
            print(f"Warning - Could not load plan.xml: {e}")

    async def connect(self):
        try:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            self.connected = True
            self.state["status"] = "online"
            asyncio.create_task(self.listen())
            print("Successfully connected to Rocrail socket for live updates!")
        except Exception as e:
            print(f"Rocrail connection error: {e}")

    async def send_command(self, body, name):
        if not self.writer: return
        header = f'<xmlh><xml size="{len(body)}" name="{name}"/></xmlh>'
        self.writer.write((header + body).encode('utf-8'))
        await self.writer.drain()

    async def listen(self):
        buffer = ""
        while self.connected:
            try:
                data = await self.reader.read(4096)
                if not data: break
                
                buffer += data.decode('utf-8', errors='ignore')
                
                # If Rocrail broadcasts a speed change, update our in-memory state
                for match in re.finditer(r'<lc id="([^"]+)"[^>]*V="([^"]*)"', buffer):
                    loc_id, speed = match.groups()
                    if loc_id in self.state["locomotives"]:
                        self.state["locomotives"][loc_id]["speed"] = speed
                        
                if len(buffer) > 100000: buffer = ""
            except Exception:
                break

    def disconnect(self):
        self.connected = False
        if self.writer: self.writer.close()

    def get_state(self):
        return self.state