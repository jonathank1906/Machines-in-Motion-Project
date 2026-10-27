"""What visitors are allowed to touch. Edit this when the lab tells you which loco/switches to expose.
Empty sets mean NOTHING is allowed (fail closed)."""
ALLOWED_LOCOS = {"BR103", "NS2418"}
ALLOWED_SWITCHES = {"sw1", "sw2"}
MAX_SPEED = 60                       # percent cap, enforced server-side