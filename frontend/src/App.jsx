import { useState, useEffect, useRef } from "react"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
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
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Moon,
  OctagonX,
  Sun,
  Train,
  Split,
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

/* ---------- app ---------- */

export default function App() {
  const { theme, toggle } = useTheme()

  const [liveState, setLiveState] = useState({ locomotives: {}, switches: {} })
  const [allowed, setAllowed] = useState({ locos: [], switches: [] })
  const [selectedLoco, setSelectedLoco] = useState("")
  const [selectedSwitch, setSelectedSwitch] = useState("")
  const [localSpeed, setLocalSpeed] = useState(0)

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
        .then((res) => res.json())
        .then((data) => setLiveState(data))
        .catch((err) => console.error("Polling error:", err))
    }, 1000)
    return () => clearInterval(interval)
  }, [])

  // Clear any pending speed command on unmount
  useEffect(() => () => clearTimeout(debounceTimer.current), [])

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
    fetch(path, { method: "POST" }).catch((err) =>
      console.error("Request error:", err)
    )

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
          <div className="flex items-center gap-2.5">
            <Train className="h-5 w-5" />
            <h1 className="text-lg font-semibold tracking-tight">
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
        {/* Emergency stop */}
        <Button
          variant="destructive"
          onClick={emergencyStop}
          className="h-20 w-full gap-3 text-xl font-bold"
        >
          <AlertTriangle className="h-7 w-7" />
          Emergency stop all trains
        </Button>

        <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
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
                <Select value={selectedLoco} onValueChange={setSelectedLoco}>
                  <SelectTrigger id="loco-select" className="w-full">
                    <SelectValue placeholder="Select a train…" />
                  </SelectTrigger>
                  <SelectContent>
                    {allowed.locos.map((id) => (
                      <SelectItem key={id} value={id}>
                        {id}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
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
                      disabled={!selectedLoco}
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
                    <Badge variant="secondary" className="mt-3 capitalize">
                      {activeLoco.direction}
                    </Badge>
                  </div>

                  <div className="space-y-2">
                    <Label>Direction</Label>
                    <ToggleGroup
                      type="single"
                      variant="outline"
                      value={activeLoco.direction}
                      onValueChange={setDirection}
                      disabled={!selectedLoco}
                      className="w-full"
                    >
                      <ToggleGroupItem value="reverse" className="flex-1 gap-1.5">
                        <ArrowLeft className="h-4 w-4" />
                        Reverse
                      </ToggleGroupItem>
                      <ToggleGroupItem value="forward" className="flex-1 gap-1.5">
                        <ArrowRight className="h-4 w-4" />
                        Forward
                      </ToggleGroupItem>
                    </ToggleGroup>
                  </div>
                </div>
              </div>
            </CardContent>

            <CardFooter>
              <Button
                variant="secondary"
                className="w-full gap-2"
                onClick={stopLoco}
                disabled={!selectedLoco}
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
                <Select value={selectedSwitch} onValueChange={setSelectedSwitch}>
                  <SelectTrigger id="switch-select" className="w-full">
                    <SelectValue placeholder="Select a switch…" />
                  </SelectTrigger>
                  <SelectContent>
                    {allowed.switches.map((id) => (
                      <SelectItem key={id} value={id}>
                        Switch: {id}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
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
                disabled={!selectedSwitch}
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