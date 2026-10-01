"""Command seam between the API and Rocrail. Mix into RocrailAdapter:
    class RocrailAdapter(CommandsMixin): ...
All validation and the speed cap live here, so the browser is never trusted."""
from xml.sax.saxutils import quoteattr
from backend import config


class CommandsMixin:
    def _check_loco(self, loco_id):
        if loco_id not in config.ALLOWED_LOCOS:
            raise PermissionError(f"loco '{loco_id}' is not available to visitors")

    def _check_switch(self, sw_id):
        if sw_id not in config.ALLOWED_SWITCHES:
            raise PermissionError(f"switch '{sw_id}' is not available to visitors")

    async def set_speed(self, loco_id, speed):
        self._check_loco(loco_id)
        speed = max(0, min(int(speed), config.MAX_SPEED))
        await self.send_command(f'<lc id={quoteattr(loco_id)} V="{speed}" cmd="velocity"/>', "lc")
        return speed

    async def set_direction(self, loco_id, forward):
        self._check_loco(loco_id)
        # One command: speed 0 AND the new direction, so a loco never reverses at speed.
        # (Same form Rocview's throttle uses.)
        d = "true" if forward else "false"
        await self.send_command(
            f'<lc id={quoteattr(loco_id)} V="0" dir="{d}" cmd="velocity"/>', "lc")

    async def stop(self, loco_id):
        self._check_loco(loco_id)
        # Rocrail's cmd="stop" did not zero the speed in testing; velocity 0 does.
        await self.send_command(f'<lc id={quoteattr(loco_id)} V="0" cmd="velocity"/>', "lc")

    async def emergency_stop_all(self):
        """Stops every allowed loco. Not subject to claims; anyone may call it."""
        for loco_id in config.ALLOWED_LOCOS:
            await self.send_command(f'<lc id={quoteattr(loco_id)} V="0" cmd="velocity"/>', "lc")

    async def throw_switch(self, sw_id, position="flip"):
        self._check_switch(sw_id)
        if position not in ("flip", "straight", "turnout"):
            raise ValueError("position must be flip, straight or turnout")
        await self.send_command(f'<sw id={quoteattr(sw_id)} cmd="{position}"/>', "sw")