import asyncio
from xml.sax.saxutils import quoteattr
from backend import config

class EStopActive(Exception):
    """A move command was refused because the emergency stop is latched."""

class CommandsMixin:
    def _ctl(self):
        if not hasattr(self, "_ctl_state"):
            self._ctl_state = {"estop": False, "locks": {}, "intent": {}}
        return self._ctl_state

    def _lock(self, loco_id):
        return self._ctl()["locks"].setdefault(loco_id, asyncio.Lock())

    def _intent(self, loco_id):
        return self._ctl()["intent"].setdefault(
            loco_id, {"speed": 0, "forward": None, "light": None})

    @property
    def estop_active(self):
        return self._ctl()["estop"]

    def _check_loco(self, loco_id):
        if loco_id not in config.ALLOWED_LOCOS:
            raise PermissionError(f"loco '{loco_id}' is not available to visitors")

    def _check_switch(self, sw_id):
        if sw_id not in config.ALLOWED_SWITCHES:
            raise PermissionError(f"switch '{sw_id}' is not available to visitors")

    async def _send_lc(self, loco_id, intent):
        """Send the full intended state of one loco in a single velocity packet."""
        attrs = f'V="{intent["speed"]}"'
        if intent["forward"] is not None:
            direction = "true" if intent["forward"] else "false"
            attrs += f' dir="{direction}"'
        if intent["light"] is not None:
            light = "true" if intent["light"] else "false"
            attrs += f' fn="{light}"'
        await self.send_command(
            f'<lc id={quoteattr(loco_id)} cmd="velocity" {attrs}/>', "lc")

    def _mirror_stop(self, loco_id):
        """Make the UI show the stop immediately, before Rocrail's echo arrives."""
        locos = getattr(self, "state", {}).get("locomotives", {})
        if loco_id in locos:
            locos[loco_id]["speed"] = 0
            locos[loco_id]["mode"] = "stop"

    async def set_speed(self, loco_id, speed):
        self._check_loco(loco_id)
        speed = max(0, min(int(speed), config.MAX_SPEED))
        async with self._lock(loco_id):
            if speed > 0 and self.estop_active:
                raise EStopActive("emergency stop is active: reset it before driving")
            intent = self._intent(loco_id)
            intent["speed"] = speed
            await self._send_lc(loco_id, intent)
        return speed

    async def set_direction(self, loco_id, forward):
        self._check_loco(loco_id)
        async with self._lock(loco_id):
            intent = self._intent(loco_id)
            intent["speed"] = 0         
            intent["forward"] = bool(forward)
            await self._send_lc(loco_id, intent)

    async def stop(self, loco_id):
        self._check_loco(loco_id)
        async with self._lock(loco_id):
            intent = self._intent(loco_id)
            intent["speed"] = 0
            await self._send_lc(loco_id, intent)

    async def set_light(self, loco_id, light_on):
        self._check_loco(loco_id)
        async with self._lock(loco_id):
            intent = self._intent(loco_id)
            intent["light"] = bool(light_on)
            if self.estop_active:
                intent["speed"] = 0
            await self._send_lc(loco_id, intent)

    async def emergency_stop_all(self):
        """Latch the stop first, then stop every allowed loco. Tries everything
        even if one send fails, and re-raises the first error afterwards."""
        self._ctl()["estop"] = True     
        first_error = None
        for loco_id in sorted(config.ALLOWED_LOCOS):
            try:
                async with self._lock(loco_id):  
                    intent = self._intent(loco_id)
                    intent["speed"] = 0
                    self._mirror_stop(loco_id)
                    await self.send_command(f'<lc id={quoteattr(loco_id)} cmd="stop"/>', "lc")
                    await self._send_lc(loco_id, intent)
            except Exception as exc:
                first_error = first_error or exc
        try:
            await asyncio.sleep(0.1)
            await self.send_command('<sys cmd="ebreak"/>', "sys")
        except Exception as exc:
            first_error = first_error or exc
        if first_error:
            raise first_error

    async def reset_estop(self):
        """A deliberate human action: allow driving again."""
        self._ctl()["estop"] = False

    async def throw_switch(self, sw_id, position="flip"):
        self._check_switch(sw_id)
        if position not in ("flip", "straight", "turnout"):
            raise ValueError("position must be flip, straight or turnout")
        await self.send_command(f'<sw id={quoteattr(sw_id)} cmd="{position}"/>', "sw")