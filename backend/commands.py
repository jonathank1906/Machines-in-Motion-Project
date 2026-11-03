"""Command seam between the API and Rocrail. Mix into RocrailAdapter:
    class RocrailAdapter(CommandsMixin): ...
All validation and the speed cap live here, so the browser is never trusted."""
import time
import asyncio
from xml.sax.saxutils import quoteattr
from backend import config


class CommandsMixin:
    _zero_locked_locos = set()
    _estop_lockout_until = 0.0

    def _check_loco(self, loco_id):
        if loco_id not in config.ALLOWED_LOCOS:
            raise PermissionError(f"loco '{loco_id}' is not available to visitors")

    def _check_switch(self, sw_id):
        if sw_id not in config.ALLOWED_SWITCHES:
            raise PermissionError(f"switch '{sw_id}' is not available to visitors")

    async def set_speed(self, loco_id, speed):
        self._check_loco(loco_id)
        speed = max(0, min(int(speed), config.MAX_SPEED))

        # THE VAULT: If E-stopped, absolutely no speeds > 0 are allowed.
        # To drive again, the human MUST tap the slider at 0 to prove they are present,
        # which sends a speed=0 packet and clears the lock.
        if loco_id in self.__class__._zero_locked_locos:
            if speed > 0:
                print(f">> SAFETY INTERLOCK: Blocked ghost speed {speed}")
                return 0
            else:
                print(f">> SYSTEM RESET: Human acknowledged 0, lifting lock for {loco_id}")
                self.__class__._zero_locked_locos.remove(loco_id)

        # Standard 2-second debouncer shield
        if time.time() < self.__class__._estop_lockout_until:
            print(f">> SAFETY INTERLOCK: Blocked lingering ghost speed {speed}")
            return 0

        await self.send_command(f'<lc id={quoteattr(loco_id)} V="{speed}" cmd="velocity"/>', "lc")
        return speed

    async def set_direction(self, loco_id, forward):
        self._check_loco(loco_id)
        d = "true" if forward else "false"
        await self.send_command(
            f'<lc id={quoteattr(loco_id)} V="0" dir="{d}" cmd="velocity"/>', "lc")

    async def stop(self, loco_id):
        self._check_loco(loco_id)
        await self.send_command(f'<lc id={quoteattr(loco_id)} V="0" cmd="velocity"/>', "lc")

    async def emergency_stop_all(self):
        """Forces hardware stop and arms the zero-lock."""
        self.__class__._estop_lockout_until = time.time() + 2.0 
        
        for loco_id in config.ALLOWED_LOCOS:
            self.__class__._zero_locked_locos.add(loco_id)
            
            if hasattr(self, 'state') and loco_id in self.state.get("locomotives", {}):
                self.state["locomotives"][loco_id]["speed"] = 0
                self.state["locomotives"][loco_id]["mode"] = "stop"
                
            await self.send_command(f'<lc id={quoteattr(loco_id)} cmd="stop"/>', "lc")
            await self.send_command(f'<lc id={quoteattr(loco_id)} V="0" cmd="velocity"/>', "lc")

        await asyncio.sleep(0.1)
        await self.send_command('<sys cmd="ebreak"/>', "sys")

    async def throw_switch(self, sw_id, position="flip"):
        self._check_switch(sw_id)
        if position not in ("flip", "straight", "turnout"):
            raise ValueError("position must be flip, straight or turnout")
        await self.send_command(f'<sw id={quoteattr(sw_id)} cmd="{position}"/>', "sw")

    async def set_light(self, loco_id, light_on):
        self._check_loco(loco_id)
        light_str = "true" if light_on else "false"
        
        current_state = self.state["locomotives"].get(loco_id, {})
        v = current_state.get("speed", 0)
        d = "true" if current_state.get("direction", "forward") == "forward" else "false"
        
        await self.send_command(
            f'<lc id={quoteattr(loco_id)} cmd="velocity" V="{v}" dir="{d}" fn="{light_str}"/>', 
            "lc"
        )