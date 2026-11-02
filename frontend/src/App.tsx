import { Toaster } from "sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { BentoGrid } from "@/components/BentoGrid";

export default function App() {
  return (
    <TooltipProvider delayDuration={200}>
      <BentoGrid />
      <Toaster theme="dark" richColors position="bottom-right" />
    </TooltipProvider>
  );
}
