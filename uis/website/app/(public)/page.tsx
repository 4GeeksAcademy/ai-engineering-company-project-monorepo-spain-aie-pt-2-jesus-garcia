import { HeroSection } from "@/components/HeroSection";
import { StatsSection } from "@/components/StatsSection";
import { TimelineSection } from "@/components/TimelineSection";
import { CTASection } from "@/components/CTASection";

export default function HomePage() {
  return (
    <>
      <HeroSection />
      <StatsSection />
      <TimelineSection />
      <CTASection />
    </>
  );
}
