# AI Running Coach — Design Tokens (from android/ui/theme)

Source: dallariva93/AI-personal-running-coach @ claude/running-analytics-platform-a017s4
Kotlin/Jetpack Compose Material 3 app. Font = platform SansSerif (system-ui).

## Brand
- BrandGreen #00C16E · BrandGreenBright #2BE38C · BrandGreenDeep #037A45
- Coral #FF5A1F · CoralBright #FF7E45

## Dark theme (default/primary look — near-black, cool)
- background #0D1014 · surface #161B22 · surfaceElevated #1D232C · surfaceVariant #242C37
- outline #323B47 · onSurface #E7ECF2 · onSurfaceMuted #9AA6B4
- primary=BrandGreen, onPrimary #00210F, primaryContainer=BrandGreenDeep, onPrimaryContainer=BrandGreenBright
- secondary=Coral

## Light theme
- background #F5F7FA · surface #FFFFFF · surfaceVariant #EDF1F5
- outline #D7DEE6 · onSurface #11161C · onSurfaceMuted #5C6773
- primary=BrandGreenDeep, primaryContainer #B9F6CA

## Form state (TSB/forma ring + badges)
- fresh #22C55E · balanced #38BDF8 · fatigued #F43F5E · detraining #FBBF24 · unknown #64748B

## HR zones / intensity
- Z1 #64748B (recovery) · Z2 #38BDF8 (easy) · Z3 #22C55E (moderate) · Z4 #FB923C (threshold) · Z5 #F43F5E (VO2)

## Risk traffic-light
- low #22C55E · moderate #FBBF24 · high #F43F5E

## Activity-type badge (easy→hard)
- easy/recupero #22C55E · medio/lungo #38BDF8 · tempo #FB923C · intervalli/gara #F43F5E · trail #10B981

## Shapes (radii)
- xs 8 · sm 12 · md 18 · lg 24 · xl 32 (dp)

## Type scale (system sans)
- displaySmall 40/44 Black, -0.5 (hero numeric metrics)
- headlineMedium 26/32 Bold -0.3 · headlineSmall 22/28 Bold -0.2
- titleLarge 19/24 Bold · titleMedium 16/22 SemiBold
- bodyLarge 15/22 · bodyMedium 14/20 · bodySmall 13/18 (Normal)
- labelLarge 14/18 SemiBold · labelMedium 12/16 SemiBold +0.4 · labelSmall 11/14 Medium +0.4

## Notes
- dynamicColor OFF; brand colors always. Dark mode is the signature look.
- Large rounded cards central to "premium" look. Transparent status/nav bars.
