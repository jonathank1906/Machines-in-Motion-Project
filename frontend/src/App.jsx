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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Moon,
  OctagonX,
  Sun,
  Train,
  Split,
  WifiOff,
} from "lucide-react"

/* ---------- theme ---------- */

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

/* ---------- connection status ---------- */

const STATUS = {
  online: { label: "Connected", dot: "bg-emerald-500", ping: true },
  connecting: { label: "Connecting…", dot: "bg-amber-500", ping: true },
  offline: { label: "Offline", dot: "bg-red-500", ping: false },
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

/* ---------- picker: plain label for one option, dropdown for several ---------- */

function Picker({ id, value, onChange, options, placeholder, disabled, format = (v) => v }) {
  if (options.length <= 1) {
    return (
      <div
        id={id}
        className={`flex h-9 w-full items-center rounded-md border bg-muted/50 px-3 text-sm ${disabled ? "opacity-50" : ""}`}
      >
        {options.length ? (
          format(options[0])
        ) : (
          <span className="text-muted-foreground">None available</span>
        )}
      </div>
    )
  }
  return (
    <Select value={value} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger id={id} className="w-full">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map((opt) => (
          <SelectItem key={opt} value={opt}>
            {format(opt)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

/* ---------- app ---------- */

export default function App() {
  const { theme, toggle } = useTheme()

  const [liveState, setLiveState] = useState({ locomotives: {}, switches: {} })
  const [allowed, setAllowed] = useState({ locos: [], switches: [] })
  const [selectedLoco, setSelectedLoco] = useState("")
  const [selectedSwitch, setSelectedSwitch] = useState("")
  const [localSpeed, setLocalSpeed] = useState(0)
  const [failures, setFailures] = useState(0)
  const [hasConnected, setHasConnected] = useState(false)

  const debounceTimer = useRef(null)
  const lastSendTime = useRef(0)
  const syncLock = useRef(false)

  // Load which locomotives and switches this panel may control
  useEffect(() => {
    fetch("/api/allowed")
      .then((res) => res.json())
      .then((data) => {
        setAllowed({
          locos: data.locos ?? [],
          switches: data.switches ?? [],
        })
        if (data.locos?.length > 0) setSelectedLoco(data.locos[0])
        if (data.switches?.length > 0) setSelectedSwitch(data.switches[0])
      })
      .catch((err) => console.error("Config fetch error:", err))
  }, [])

  // Poll live state every second
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

  // Clear any pending speed command on unmount
  useEffect(() => () => clearTimeout(debounceTimer.current), [])

  // Offline = the API stopped answering twice in a row, or the backend
  // reports that it lost Rocrail (state.status === "offline")
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

  // Follow the server's speed unless the user is mid-drag
  useEffect(() => {
    if (activeLoco.speed !== undefined && !syncLock.current) {
      setLocalSpeed(activeLoco.speed)
    }
  }, [activeLoco.speed, selectedLoco])

  const post = (path) =>
    fetch(path, { method: "POST" }).catch((err) => {
      console.error("Request error:", err)
      setFailures((f) => Math.max(f, 2)) // command didn't reach the server
    })

  const handleSpeedChange = ([speed]) => {
    setLocalSpeed(speed)
    syncLock.current = true

    // Throttled live updates while dragging
    const now = Date.now()
    if (now - lastSendTime.current > 100) {
      lastSendTime.current = now
      if (selectedLoco) post(`/api/loco/${selectedLoco}/speed/${speed}`)
    }

    // Final value once the user pauses
    clearTimeout(debounceTimer.current)
    debounceTimer.current = setTimeout(() => {
      if (selectedLoco) {
        post(`/api/loco/${selectedLoco}/speed/${speed}`).finally(() =>
          setTimeout(() => {
            syncLock.current = false
          }, 500)
        )
      }
    }, 150)
  }

  const setDirection = (dir) => {
    if (!selectedLoco || !dir) return
    post(`/api/loco/${selectedLoco}/direction/${dir}`)
  }

  const stopLoco = () => {
    if (!selectedLoco) return
    post(`/api/loco/${selectedLoco}/stop`)
    setLocalSpeed(0)
  }

  const emergencyStop = () => {
    // Cancel any queued speed command so it can't override the stop
    clearTimeout(debounceTimer.current)
    syncLock.current = false
    post("/api/estop")
    setLocalSpeed(0)
  }

  const flipSwitch = () => {
    if (!selectedSwitch) return
    post(`/api/switch/${selectedSwitch}/flip`)
  }

  return (
    <div className={theme === "dark" ? "dark" : ""}>
    <div className="min-h-screen bg-background text-foreground">
      {/* Header */}
      <header className="border-b">
        <div className="mx-auto flex h-16 max-w-4xl items-center justify-between px-6">
          <div className="flex items-center gap-4">
            <ConnectionStatus status={status} />
            <Separator orientation="vertical" className="hidden h-5 sm:block" />
            <h1 className="hidden text-lg font-semibold tracking-tight sm:block">
              Rail Exhibit Control
            </h1>
          </div>
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

      <main className="mx-auto max-w-4xl space-y-6 p-6">
        {offline && (
          <Alert variant="destructive">
            <WifiOff />
            <AlertTitle>Connection lost</AlertTitle>
            <AlertDescription>
              Train and switch controls are paused until the connection
              returns.
            </AlertDescription>
          </Alert>
        )}

        {/* Emergency stop */}
        <Button
          onClick={emergencyStop}
          className="h-14 w-full gap-2.5 rounded-xl border border-red-900 bg-red-600 text-lg font-bold text-white shadow-[0_4px_0_0_#7f1d1d] transition-[transform,box-shadow] hover:bg-red-700 active:translate-y-1 active:shadow-none dark:border-red-950 dark:bg-red-600 dark:hover:bg-red-700"
        >
          <AlertTriangle className="h-5 w-5" />
          Emergency stop all trains
        </Button>

        <div
          className={`grid grid-cols-1 gap-6 transition-opacity md:grid-cols-2 ${offline ? "opacity-60" : ""}`}
        >
          {/* Train control */}
          <Card className="flex flex-col border bg-card text-card-foreground shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Train className="h-5 w-5" />
                Train control
              </CardTitle>
              <CardDescription>
                Set speed and direction for the selected locomotive.
              </CardDescription>
            </CardHeader>

            <CardContent className="flex flex-1 flex-col gap-6">
              <div className="space-y-2">
                <Label htmlFor="loco-select">Active train</Label>
                <Picker
                  id="loco-select"
                  value={selectedLoco}
                  onChange={setSelectedLoco}
                  options={allowed.locos}
                  placeholder="Select a train…"
                  disabled={offline}
                />
              </div>

              <Separator />

              <div className="flex flex-1 items-stretch gap-8">
                {/* Vertical throttle */}
                <div className="flex flex-col items-center gap-3">
                  <Label htmlFor="throttle">Throttle</Label>
                  <div className="flex h-64 justify-center">
                    <Slider
                      id="throttle"
                      orientation="vertical"
                      value={[localSpeed]}
                      max={100}
                      step={1}
                      onValueChange={handleSpeedChange}
                      disabled={!selectedLoco || offline}
                      className="h-full"
                      aria-label="Throttle"
                    />
                  </div>
                </div>

                {/* Readout + direction */}
                <div className="flex flex-1 flex-col justify-between gap-6">
                  <div className="space-y-1">
                    <p className="text-sm text-muted-foreground">Speed</p>
                    <p className="font-mono text-6xl font-semibold tabular-nums leading-none">
                      {localSpeed}
                      <span className="ml-1 text-2xl text-muted-foreground">
                        %
                      </span>
                    </p>
                  </div>

                  <div className="space-y-2">
                    <Label>Direction</Label>
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
                          disabled={!selectedLoco || offline}
                          onClick={() => setDirection(dir)}
                        >
                          <Icon className="h-4 w-4" />
                          {label}
                        </Button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </CardContent>

            <CardFooter>
              <Button
                variant="secondary"
                className="w-full gap-2"
                onClick={stopLoco}
                disabled={!selectedLoco || offline}
              >
                <OctagonX className="h-4 w-4" />
                Halt train
              </Button>
            </CardFooter>
          </Card>

          {/* Track routing */}
          <Card className="flex flex-col border bg-card text-card-foreground shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Split className="h-5 w-5" />
                Track routing
              </CardTitle>
              <CardDescription>
                Move the physical switches on the exhibit table.
              </CardDescription>
            </CardHeader>

            <CardContent className="flex flex-1 flex-col gap-6">
              <div className="space-y-2">
                <Label htmlFor="switch-select">Target switch</Label>
                <Picker
                  id="switch-select"
                  value={selectedSwitch}
                  onChange={setSelectedSwitch}
                  options={allowed.switches}
                  placeholder="Select a switch…"
                  disabled={offline}
                  format={(id) => `Switch: ${id}`}
                />
              </div>

              <div className="rounded-lg border bg-muted/50 p-4 text-sm text-muted-foreground">
                <p className="mb-1 font-medium text-foreground">
                  Watch the physical table.
                </p>
                The rails move as soon as you press the button below, changing
                the path of any train on the track.
              </div>
            </CardContent>

            <CardFooter>
              <Button
                className="w-full"
                onClick={flipSwitch}
                disabled={!selectedSwitch || offline}
              >
                Flip switch
              </Button>
            </CardFooter>
          </Card>
        </div>
      </main>
    </div>
    </div>
  )
}