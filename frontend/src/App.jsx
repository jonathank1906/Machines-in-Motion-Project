import { useState, useEffect, useRef } from "react"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Slider } from "@/components/ui/slider"
import { Switch } from "@/components/ui/switch"
import {
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer"
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Menu,
  Moon,
  OctagonX,
  Sun,
  Train,
  Split,
  WifiOff,
  Lightbulb,
} from "lucide-react"
import darkModeTracks from "@/assets/Dark Mode Train Tracks.svg"
import lightModeTracks from "@/assets/Light Mode Train Tracks.svg"

function useTheme() {
  const [theme, setTheme] = useState(() => {
    try {
      const saved = localStorage.getItem("theme")
      if (saved === "light" || saved === "dark") return saved
    } catch {}
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light"
  })

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark")
    document.documentElement.style.colorScheme = theme
    try {
      localStorage.setItem("theme", theme)
    } catch {}
  }, [theme])

  const toggle = () => setTheme((t) => (t === "dark" ? "light" : "dark"))
  return { theme, toggle }
}

const STATUS = {
  online: { label: "Connected", dot: "bg-emerald-500", ping: true },
  connecting: { label: "Connecting", dot: "bg-amber-500", ping: true },
  offline: { label: "Offline", dot: "bg-red-500", ping: false },
}

function LocoThumbnail({ locoId, imageName, roadname }) {
  const src = imageName
    ? `/rocrail-images/${imageName}`
    : `/rocrail-images/${locoId.toLowerCase()}.png`
  const [imageFailed, setImageFailed] = useState(false)

  useEffect(() => {
    setImageFailed(false)
  }, [src])

  if (imageFailed) return null

  return (
    <img
      src={src}
      alt={roadname || locoId}
      className="h-20 w-32 object-contain"
      onError={() => setImageFailed(true)}
    />
  )
}

function LocoDrawer({ open, onClose, locos, liveState, selectedLoco, onSelect }) {
  return (
    <Drawer
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose()
      }}
      swipeDirection="right"
    >
      <DrawerContent
        id="train-fleet-drawer"
        aria-label="Train fleet"
        className="w-full max-w-sm p-6"
      >
        <DrawerHeader className="p-0">
          <DrawerTitle>Train fleet</DrawerTitle>
          <DrawerDescription>Select a train to control.</DrawerDescription>
        </DrawerHeader>

        <div className="mt-6 flex flex-col gap-3 overflow-y-auto">
          {locos.map((locoId) => {
            const loco = liveState.locomotives?.[locoId] || {}
            const selected = locoId === selectedLoco
            return (
              <button
                type="button"
                key={locoId}
                disabled={loco.status === "offline"}
                className={`flex items-center gap-3 rounded-lg border p-3 text-left transition-colors ${
                  loco.status === "offline"
                    ? "pointer-events-none opacity-40"
                    : selected
                      ? "border-primary bg-primary/10"
                      : "hover:bg-muted"
                }`}
                onClick={() => {
                  onSelect(locoId)
                  onClose()
                }}
              >
                <LocoThumbnail
                  locoId={locoId}
                  imageName={loco.image}
                  roadname={loco.roadname}
                />
                <span className="min-w-0">
                  <span className="block truncate font-medium">
                    {loco.roadname || locoId}
                  </span>
                  <span className="block truncate text-sm text-muted-foreground">
                    {loco.desc || locoId}
                  </span>
                  <span className={`mt-1 block text-xs ${
                    loco.status === "offline"
                      ? "font-medium text-red-500"
                      : "text-muted-foreground"
                  }`}>
                    {loco.status === "offline"
                      ? "Train offline"
                      : `${loco.speed ?? 0}% · ${loco.direction || "forward"}`}
                  </span>
                </span>
              </button>
            )
          })}
        </div>
      </DrawerContent>
    </Drawer>
  )
}

function ConnectionStatus({ status }) {
  const { label, dot, ping } = STATUS[status]
  return (
    <Badge
      variant="outline"
      role="status"
      className="gap-2 rounded-full px-3 py-1 text-sm font-medium"
    >
      <span className="relative flex h-2 w-2">
        {ping && (
          <span
            className={`absolute inline-flex h-full w-full animate-ping rounded-full opacity-75 ${dot}`}
          />
        )}
        <span className={`relative inline-flex h-2 w-2 rounded-full ${dot}`} />
      </span>
      {label}
    </Badge>
  )
}

export default function App() {
  const { theme, toggle } = useTheme()
  const tracks = theme === "dark" ? darkModeTracks : lightModeTracks

  const [liveState, setLiveState] = useState({ locomotives: {}, switches: {} })
  const [allowed, setAllowed] = useState({ locos: [], switches: [] })
  const [selectedLoco, setSelectedLoco] = useState("")
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [localSpeed, setLocalSpeed] = useState(0)
  const [lightsState, setLightsState] = useState({})
  const lightOn = lightsState[selectedLoco] || false
  const [failures, setFailures] = useState(0)
  const [hasConnected, setHasConnected] = useState(false)
  const locoRef = useRef("")
  locoRef.current = selectedLoco
  const estop = !!liveState.estop

  const releaseTimer = useRef(null)
  const syncLock = useRef(false)
  const desiredSpeed = useRef(0)
  const pendingSend = useRef(false)
  const inFlight = useRef(false)
  const lastSendAt = useRef(0)

  useEffect(() => {
    fetch("/api/allowed")
      .then((res) => res.json())
      .then((data) => {
        setAllowed({
          locos: data.locos ?? [],
          switches: data.switches ?? [],
        })
        if (data.locos?.length > 0) setSelectedLoco(data.locos[0])
      })
      .catch((err) => console.error("Config fetch error:", err))
  }, [])

  useEffect(() => {
    const interval = setInterval(() => {
      fetch("/api/state")
        .then((res) => {
          if (!res.ok) throw new Error(`State request failed (${res.status})`)
          return res.json()
        })
        .then((data) => {
          setLiveState(data)
          setFailures(0)
          setHasConnected(true)
        })
        .catch((err) => {
          console.error("Polling error:", err)
          setFailures((f) => f + 1)
        })
    }, 1000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => () => clearTimeout(releaseTimer.current), [])

  const status =
    failures >= 2 || liveState.status === "offline"
      ? "offline"
      : hasConnected
        ? "online"
        : "connecting"
  const offline = status === "offline"

  const activeLoco = liveState.locomotives?.[selectedLoco] || {
    speed: 0,
    direction: "forward",
  }
  const isSelectedOffline = activeLoco.status === "offline"

  useEffect(() => {
    clearTimeout(releaseTimer.current)
    syncLock.current = false
    pendingSend.current = false
    const locoData = liveState.locomotives?.[selectedLoco] || {}
    const targetSpeed = locoData.speed ?? 0
    desiredSpeed.current = targetSpeed
    setLocalSpeed(targetSpeed)
  }, [selectedLoco, liveState.locomotives])

  useEffect(() => {
    if (activeLoco.speed !== undefined && !syncLock.current) {
      setLocalSpeed((prevSpeed) => {
        if (activeLoco.speed === 0) return 0
        if (Math.abs(activeLoco.speed - prevSpeed) <= 2) {
          return prevSpeed
        }
        return activeLoco.speed
      })
    }
  }, [activeLoco.speed])

  const post = (path) =>
    fetch(path, { method: "POST" }).catch((err) => {
      console.error("Request error:", err)
      setFailures((f) => Math.max(f, 2))
    })

  const pumpSpeed = async () => {
    if (isSelectedOffline || offline || estop) {
      pendingSend.current = false
      return
    }
    if (inFlight.current) return
    inFlight.current = true
    const retrySoon = () => {
      pendingSend.current = true
      setTimeout(pumpSpeed, 300)
    }
    try {
      while (pendingSend.current) {
        const wait = 100 - (Date.now() - lastSendAt.current)
        if (wait > 0) await new Promise((r) => setTimeout(r, wait))
        pendingSend.current = false
        const speed = desiredSpeed.current
        lastSendAt.current = Date.now()
        const res = await fetch(`/api/loco/${locoRef.current}/speed/${speed}`, { method: "POST" })
        if (res.status === 409) {
          desiredSpeed.current = 0
          setLocalSpeed(0)
          break
        }
        if (!res.ok) {
          if (res.status >= 500) retrySoon()
          break
        }
      }
    } catch (err) {
      console.error("Request error:", err)
      setFailures((f) => Math.max(f, 2))
      retrySoon()
    } finally {
      inFlight.current = false
    }
  }

  const handleSpeedChange = ([speed]) => {
    if (isSelectedOffline || offline || estop) return
    setLocalSpeed(speed)
    syncLock.current = true
    desiredSpeed.current = speed
    pendingSend.current = true
    pumpSpeed()
    clearTimeout(releaseTimer.current)
  }

  const handleSpeedCommit = () => {
    if (isSelectedOffline || offline || estop) return
    clearTimeout(releaseTimer.current)
    releaseTimer.current = setTimeout(() => {
      syncLock.current = false
    }, 1500)
  }

  const whenIdle = async (fn) => {
    while (inFlight.current) await new Promise((r) => setTimeout(r, 20))
    fn()
  }

  const setDirection = (dir) => {
    if (!selectedLoco || !dir || isSelectedOffline || offline) return
    pendingSend.current = false
    desiredSpeed.current = 0
    whenIdle(() => post(`/api/loco/${selectedLoco}/direction/${dir}`))
  }

  const toggleLight = () => {
    if (!selectedLoco || isSelectedOffline || offline) return
    const newState = !lightOn
    setLightsState((prev) => ({ ...prev, [selectedLoco]: newState }))
    whenIdle(() => post(`/api/loco/${selectedLoco}/light/${newState}`))
  }

  const stopLoco = () => {
    if (!selectedLoco || isSelectedOffline || offline) return
    syncLock.current = true
    clearTimeout(releaseTimer.current)
    setLocalSpeed(0)
    desiredSpeed.current = 0
    pendingSend.current = true
    pumpSpeed()
    releaseTimer.current = setTimeout(() => {
      syncLock.current = false
    }, 1500)
  }

  const emergencyStop = () => {
    pendingSend.current = false
    desiredSpeed.current = 0
    clearTimeout(releaseTimer.current)
    syncLock.current = false
    setLocalSpeed(0)
    post("/api/estop")
  }

  const resetEstop = () => post("/api/estop/reset")

  const setSwitchPosition = (switchId, turnout) => {
    post(`/api/switch/${switchId}/${turnout ? "turnout" : "straight"}`)
  }

  return (
    <div className={theme === "dark" ? "dark" : ""}>
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="border-b">
        <div className="relative mx-auto flex h-16 max-w-4xl items-center justify-between px-6">
          <div className="flex items-center gap-4">
            <ConnectionStatus status={status} />
            <Separator orientation="vertical" className="hidden h-5 sm:block" />
          </div>
          <h1 className="absolute left-1/2 hidden -translate-x-1/2 text-lg font-semibold tracking-tight sm:block">
            Lego Rail Exhibit Control
          </h1>
          <Button
            variant="outline"
            size="icon"
            onClick={toggle}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          >
            {theme === "dark" ? (
              <Sun className="h-4 w-4" />
            ) : (
              <Moon className="h-4 w-4" />
            )}
          </Button>
        </div>
      </header>

      <LocoDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        locos={allowed.locos}
        liveState={liveState}
        selectedLoco={selectedLoco}
        onSelect={setSelectedLoco}
      />

      <main className="mx-auto w-full max-w-4xl flex-1 space-y-6 p-6">
        {offline && (
          <Alert variant="destructive">
            <WifiOff />
            <AlertTitle>Connection lost</AlertTitle>
            <AlertDescription>
              Train controls are not available.
            </AlertDescription>
          </Alert>
        )}
        {estop && (
          <Alert variant="destructive">
            <AlertTriangle />
            <AlertTitle>Emergency stop active</AlertTitle>
            <AlertDescription className="flex items-center justify-between gap-4">
              All trains are stopped and locked.
              <Button size="sm" onClick={resetEstop}>Reset and drive</Button>
            </AlertDescription>
          </Alert>
        )}

        <Button
          variant="destructive"
          onClick={emergencyStop}
          className="h-14 w-full gap-2.5 bg-red-700 text-lg font-bold text-white hover:bg-red-800 dark:bg-red-900 dark:hover:bg-red-950"
        >
          Emergency stop all trains
        </Button>

        <div
          className={`grid grid-cols-1 gap-6 transition-opacity md:grid-cols-[12rem_minmax(0,1fr)] ${offline ? "opacity-60" : ""}`}
        >
          <Card className="relative order-1 flex flex-col overflow-hidden border bg-card text-card-foreground shadow-sm md:order-2">
            {isSelectedOffline && (
              <div className="absolute inset-x-0 top-0 z-10 flex items-center gap-2 border-b border-red-600/20 bg-red-600/10 px-4 py-2.5 text-xs font-medium text-red-600">
                <span className="h-2 w-2 animate-pulse rounded-full bg-red-600" />
                Train {selectedLoco} is currently offline.
              </div>
            )}
            <CardHeader className={isSelectedOffline ? "pt-14" : undefined}>
              <CardTitle className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2">
                  <Train className="h-5 w-5" />
                  Train control
                </span>
                <Button
                  size="lg"
                  className="gap-2 px-5"
                  onClick={() => setDrawerOpen(true)}
                  aria-expanded={drawerOpen}
                  aria-controls="train-fleet-drawer"
                >
                  Trains
                </Button>
              </CardTitle>
              <CardDescription className="text-xs">
                Set the speed, direction, and lights for the selected train.
              </CardDescription>
              {selectedLoco && (
                <div className="flex flex-col items-center gap-3 pt-2 text-center">
                  <LocoThumbnail
                    locoId={selectedLoco}
                    imageName={activeLoco.image}
                    roadname={activeLoco.roadname}
                  />
                  <div className="text-sm text-muted-foreground">
                    <p className="font-medium text-foreground">
                      {activeLoco.roadname
                        ? `${activeLoco.roadname} - ${selectedLoco}`
                        : selectedLoco}
                    </p>
                    {activeLoco.desc && <p>{activeLoco.desc}</p>}
                  </div>
                </div>
              )}
            </CardHeader>

            <CardContent
              className={`flex flex-1 flex-col gap-6 transition-opacity ${
                isSelectedOffline ? "pointer-events-none opacity-40" : ""
              }`}
            >
              <div className="flex flex-1 justify-center gap-12 py-4 sm:gap-24">
                <div className="flex w-16 flex-col items-center gap-4">
                  <Label htmlFor="throttle" className="text-muted-foreground">Throttle</Label>
                  <div className="flex h-64 items-stretch justify-center gap-3">
                    <div
                      aria-hidden="true"
                      className="flex h-full flex-col justify-between py-1 text-xs text-muted-foreground"
                    >
                      {[60, 50, 40, 30, 20, 10, 0].map((speed) => (
                        <div key={speed} className="flex items-center gap-1">
                          <span className="w-5 text-right">{speed}</span>
                          <span className="h-px w-3 bg-muted-foreground/60" />
                        </div>
                      ))}
                    </div>
                    <Slider
                      id="throttle"
                      orientation="vertical"
                      value={[localSpeed]}
                      max={60}
                      step={1}
                      onValueChange={handleSpeedChange}
                      onValueCommit={handleSpeedCommit}
                      disabled={!selectedLoco || isSelectedOffline || offline || estop}
                      className="h-full"
                      aria-label="Throttle"
                    />
                  </div>
                </div>

                <div className="flex w-full max-w-xs flex-col justify-center gap-8">
                  <div className="space-y-1">
                    <p className="text-sm text-muted-foreground">Speed</p>
                    <p className="font-mono text-7xl font-semibold tabular-nums leading-none">
                      {localSpeed}
                      <span className="ml-2 text-3xl text-muted-foreground">
                        %
                      </span>
                    </p>
                  </div>

                  <div className="space-y-6">
                    <div className="space-y-3">
                      <Label className="text-muted-foreground">Direction</Label>
                      <div className="flex w-full gap-2">
                        {[
                          { dir: "reverse", label: "Reverse", Icon: ArrowLeft },
                          { dir: "forward", label: "Forward", Icon: ArrowRight },
                        ].map(({ dir, label, Icon }) => (
                          <Button
                            key={dir}
                            variant={activeLoco.direction === dir ? "default" : "outline"}
                            className="flex-1 gap-1.5"
                            aria-pressed={activeLoco.direction === dir}
                            disabled={!selectedLoco || isSelectedOffline || offline}
                            onClick={() => setDirection(dir)}
                          >
                            <Icon className="h-4 w-4" />
                            {label}
                          </Button>
                        ))}
                      </div>
                    </div>

                    <div className="space-y-3">
                      <Label className="text-muted-foreground">Headlights</Label>
                      <Button
                        variant={lightOn ? "default" : "outline"}
                        className="w-full gap-2"
                        disabled={!selectedLoco || isSelectedOffline || offline}
                        onClick={toggleLight}
                      >
                        <Lightbulb className="h-4 w-4" />
                        {lightOn ? "Turn Lights Off" : "Turn Lights On"}
                      </Button>
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>

            <CardFooter
              className={`border-0 bg-red-700 p-0 dark:bg-red-900 ${
                isSelectedOffline ? "pointer-events-none opacity-40" : ""
              }`}
            >
              <Button
                variant="destructive"
                className="h-14 w-full rounded-none border-0 gap-2 bg-transparent text-lg font-bold text-white hover:bg-red-800 dark:hover:bg-red-950"
                onClick={stopLoco}
                disabled={!selectedLoco || isSelectedOffline || offline}
              >
                {selectedLoco ? `Stop train ${selectedLoco}` : "Stop train"}
              </Button>
            </CardFooter>
          </Card>

          <Card className="order-2 flex flex-col border bg-card text-card-foreground shadow-sm md:order-1">
            <CardHeader className="translate-y-2">
              <CardTitle className="flex items-center gap-2">
                <Split className="h-5 w-5" />
                Track routing
              </CardTitle>
              <CardDescription className="translate-y-1 text-xs">
                Control the switches in Rocrail.
              </CardDescription>
            </CardHeader>

            <CardContent className="flex flex-1 flex-col p-4">
              <div className="flex flex-col gap-4">
                {[...allowed.switches]
                  .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
                  .map((switchId) => {
                  const switchState = liveState.switches?.[switchId]?.state
                  const turnout = switchState === "turnout"
                  const switchLabel = `switch-${switchId}`
                  return (
                    <div key={switchId} className="flex items-center justify-between gap-2">
                      <Label htmlFor={switchLabel} className="truncate text-sm">
                        {switchId}
                      </Label>
                      <Switch
                        id={switchLabel}
                        checked={turnout}
                        onCheckedChange={(checked) => setSwitchPosition(switchId, checked)}
                        disabled={offline}
                        aria-label={`Set switch ${switchId} to ${turnout ? "straight" : "turnout"}`}
                      />
                    </div>
                  )
                })}
                {!allowed.switches.length && (
                  <p className="text-sm text-muted-foreground">No switches available.</p>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </main>
      <footer className="flex h-16 w-full overflow-hidden opacity-20" aria-label="Track decoration">
        {Array.from({ length: 12 }, (_, index) => (
          <img
            key={index}
            src={tracks}
            alt=""
            className={`h-full w-auto shrink-0 ${index > 0 ? "-ml-[2px]" : ""}`}
          />
        ))}
      </footer>
    </div>
    </div>
  )
}