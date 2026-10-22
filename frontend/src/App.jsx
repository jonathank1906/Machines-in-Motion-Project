import { useState, useEffect, useRef } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"

export default function App() {
  const [liveState, setLiveState] = useState({ locomotives: {} })
  const [selectedLoco, setSelectedLoco] = useState("")
  
  const [localSpeed, setLocalSpeed] = useState(0)
  const debounceTimer = useRef(null)
  const syncLock = useRef(false)

  useEffect(() => {
    const interval = setInterval(() => {
      fetch("/api/state")
        .then(res => res.json())
        .then(data => {
          setLiveState(data)
          if (!selectedLoco && data.locomotives && Object.keys(data.locomotives).length > 0) {
            setSelectedLoco(Object.keys(data.locomotives)[0])
          }
        })
        .catch(err => console.error("Polling error:", err))
    }, 1000)
    return () => clearInterval(interval)
  }, [selectedLoco])

  const activeLoco = liveState.locomotives?.[selectedLoco] || { speed: 0, direction: "forward" }

  // Sync server speed to slider only if we aren't currently dragging
  useEffect(() => {
    if (activeLoco.speed !== undefined && !syncLock.current) {
      setLocalSpeed(activeLoco.speed)
    }
  }, [activeLoco.speed])

  const handleSpeedChange = (val) => {
    const speed = val[0]
    setLocalSpeed(speed)
    syncLock.current = true // Lock incoming server updates

    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    
    debounceTimer.current = setTimeout(() => {
      if (selectedLoco) {
        fetch(`/api/loco/${selectedLoco}/speed/${speed}`, { method: "POST" })
          .catch(err => console.error("Speed command failed:", err))
          .finally(() => {
            // Unlock after a brief delay to allow server to process the command
            setTimeout(() => { syncLock.current = false }, 1000)
          })
      }
    }, 150) // 150ms debounce prevents spamming but sends reliably
  }

  const setDirection = (dir) => {
    if (!selectedLoco) return;
    fetch(`/api/loco/${selectedLoco}/direction/${dir}`, { method: "POST" })
  }

  const stopLoco = () => {
    if (!selectedLoco) return;
    fetch(`/api/loco/${selectedLoco}/stop`, { method: "POST" })
  }

  return (
    <div className="min-h-screen bg-slate-950 p-8 flex items-center justify-center">
      <Card className="w-full max-w-md bg-slate-900 text-slate-100 border-slate-800 shadow-2xl">
        <CardHeader>
          <CardTitle className="text-2xl font-bold tracking-tight text-center">Locomotive Control</CardTitle>
        </CardHeader>
        <CardContent className="space-y-8 mt-4">
          
          <div className="space-y-3">
            <label className="text-sm font-semibold text-slate-400 tracking-wide uppercase">Active Train</label>
            <select 
              className="w-full bg-slate-950 border border-slate-800 rounded-md p-3 text-slate-100 outline-none focus:border-slate-500 transition-colors"
              value={selectedLoco}
              onChange={(e) => setSelectedLoco(e.target.value)}
            >
              <option value="" disabled>Scanning for locomotives...</option>
              {Object.keys(liveState.locomotives || {}).map(id => (
                <option key={id} value={id}>{id}</option>
              ))}
            </select>
          </div>

          <div className="space-y-4">
            <div className="flex justify-between items-center text-sm font-medium">
              <span className="text-slate-400 uppercase tracking-wide">Throttle</span>
              <span className="font-mono bg-slate-950 px-2 py-1 rounded text-slate-300">{localSpeed} %</span>
            </div>
            <Slider 
              value={[localSpeed]} 
              max={100} 
              step={1}
              onValueChange={handleSpeedChange}
              className="cursor-pointer"
            />
          </div>

          <div className="space-y-3">
            <label className="text-sm font-semibold text-slate-400 tracking-wide uppercase">Direction & Stop</label>
            <div className="flex gap-4">
              <Button 
                className="flex-1 transition-all" 
                variant={activeLoco.direction === "forward" ? "default" : "outline"}
                onClick={() => setDirection("forward")}
              >
                Forward
              </Button>
              <Button 
                className="flex-1 transition-all" 
                variant={activeLoco.direction === "reverse" ? "destructive" : "outline"}
                onClick={() => setDirection("reverse")}
              >
                Reverse
              </Button>
            </div>
            <Button 
              className="w-full mt-4 transition-all" 
              variant="destructive"
              onClick={stopLoco}
            >
              STOP
            </Button>
          </div>

        </CardContent>
      </Card>
    </div>
  )
}