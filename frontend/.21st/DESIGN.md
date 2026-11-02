# X-Assistant — Design System & UI Context (.21st/DESIGN.md)

## Identity & Aesthetic Direction
- **Product**: X-Assistant — Local AI Desktop Assistant & Developer Copilot for Windows (Intel Core i3-1215U + 20 GB Flex Mode RAM).
- **Layout Archetype**: High-density **Bento Box Dark** utility interface (inspired by Raycast / Linear / Spotlight).
- **Surface Hierarchy**:
  - `--background`: Deep obsidian (`oklch(0.141 0.005 285.823)`)
  - `--card`: Elevated slate panel (`oklch(0.178 0.006 285.885)`) with `1px` `--border`
  - `--primary`: Emerald-cyan hardware accent (`oklch(0.765 0.177 163.223)`)
  - `--warning`: Amber indicator for Flex Mode (>8.5 GB) and pending security confirmations
  - `--destructive`: Crimson alert for blocked actions and RAM ejection

## Core Components (Task 15)
1. **`TelemetryCard.tsx`**: Real-time hardware monitor (CPU %, 20 GB RAM bar with 8.5 GB Dual-Channel threshold marker, Ollama RSS memory, active model badge, and one-click "Ejetar RAM" action).
2. **`QuickActions.tsx`**: 1-click developer actions (Composite Workspaces, Smart Clipboard `x-coder`, Git Commit Generator `x-fast`, Screen Vision `x-vision`) + live SQLite Audit Log feed + Sonner toasts.
3. **`ChatPanel.tsx`**: Streaming Markdown & copyable code blocks, model switcher (`ToggleGroup`: `x-fast` 3B / `x-coder` 7B / `x-vision` 4B), offline SAPI5 TTS `Switch`, inline Security Confirmation banners, and **Push-to-Talk (`MediaRecorder`)** via hold-button or `Ctrl + Space`.
4. **`AllowlistModal.tsx` & `BentoGrid.tsx`**: Full CRUD modal (`Dialog`, `Tabs`, `Input`, `Select`) for Allowed Apps, Composite Workspaces, and Monitored Git Repos where every mutation produces a server-side `confirmation_required` card.

