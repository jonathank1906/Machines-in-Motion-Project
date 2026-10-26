// src/components/ui/slider.jsx  (replace the existing file)
import * as React from "react"
import * as SliderPrimitive from "@radix-ui/react-slider"
import { cn } from "@/lib/utils"

const Slider = React.forwardRef(
  ({ className, orientation = "horizontal", ...props }, ref) => {
    const vertical = orientation === "vertical"
    return (
      <SliderPrimitive.Root
        ref={ref}
        orientation={orientation}
        className={cn(
          "relative flex touch-none select-none items-center data-[disabled]:opacity-50",
          vertical ? "h-full min-h-44 w-8 flex-col justify-center" : "w-full",
          className
        )}
        {...props}
      >
        <SliderPrimitive.Track
          className={cn(
            "relative grow overflow-hidden rounded-full border bg-muted",
            vertical ? "h-full w-3" : "h-3 w-full"
          )}
        >
          <SliderPrimitive.Range
            className={cn("absolute bg-primary", vertical ? "w-full" : "h-full")}
          />
        </SliderPrimitive.Track>
        <SliderPrimitive.Thumb className="block h-6 w-6 rounded-full border-2 border-primary bg-background shadow transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none" />
      </SliderPrimitive.Root>
    )
  }
)
Slider.displayName = "Slider"

export { Slider }