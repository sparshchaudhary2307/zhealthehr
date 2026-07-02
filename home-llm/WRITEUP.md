# Home Robot LLM - Engineering Design Writeup

## 1. Architectural Structure

To create a safe, reliable, and grounded robot agent, we designed a closed-loop **ReAct (Reasoning and Acting)** agentic system. Rather than generating a static sequence of actions upfront (open-loop planning), the agent dynamically evaluates state transitions at each execution step:

*   **Closed-Loop ReAct Loop**: The agent reads the user command, checks the robot's current state (location coordinates, currently held item, and the list of verified `known_objects`), and reviews the running step-by-step action history. This entire payload is fed to the LLM at every step (up to a limit of 15 steps per command) to generate the next action.
*   **Verification-First Grounding**: The robot is strictly constrained from manipulating any object that has not been actively sensed. If a command involves an object that is not yet in `known_objects`, the agent navigates to typical search locations first (e.g., `bathroom` for a towel, `desk` for a book, `kitchen_counter` for drinks) to explore and sense it. Only when the object appears in `known_objects` will the agent execute a `pick` action.
*   **Safety Guardrails**: The system instructions contain hardcoded safety filters that force the agent to reject requests involving hazardous objects (e.g., `kitchen_knife`, `pill_bottle`). If such an item is requested, the agent immediately uses the `speak` action to refuse the command and exits safely.
*   **Ambiguity Resolution**: If a command is vague (e.g., "bring me something to read"), the agent navigates to the typical location of those objects, senses what is available, and prompts the user for clarification (e.g., asking to choose between a book or a newspaper) instead of guessing.

---

## 2. Technical Challenges & Design Decisions

### A. Non-Blocking Pygame GUI Event Loop
*   **The Issue**: When running the interactive visual simulation via `run.py --gui`, the main execution thread blocks on the terminal's standard input (`input("\nyou> ")`). Because Pygame relies on polling window events from the main thread, the window became frozen and Windows marked it as "Not Responding" when clicked.
*   **The Solution**: We monkey-patched Python's built-in `builtins.input` function. When `input()` is called, our custom function spawns a background thread to wait for terminal keyboard input, while the **main thread** runs a high-frequency loop to poll Pygame events (`pygame.event.get()`). This keeps the GUI window fully responsive and allows users to close it cleanly.

### B. Gemini API Rate-Limit Mitigation
*   **The Issue**: The Gemini Free Tier has a sliding window limit of 15 Requests Per Minute (RPM) and a daily limit of 500 requests. When running continuous multi-step tasks, the agent easily hit transient `429 Too Many Requests` errors.
*   **The Solution**: We wrapped our API invocation in a robust retry handler utilizing exponential backoff with random jitter. If the API returns a `429`, the agent sleeps and retries up to 6 times before failing, ensuring long test suites run to completion without crashing.

### C. Visual UI Enhancements
*   **The Issue**: The original GUI map did not show room coordinates, location labels, or items until the robot was directly on top of them, and overlapping items (like the four items on the kitchen counter) drew their labels directly on top of each other, making them unreadable.
*   **The Solution**: We intercepted the Pygame renderer function. The custom renderer maps and displays room names at their geometric centers, adds labels to furniture location coordinates (excluding redundant room name overlaps), and groups items by location to stack their text labels vertically (e.g., stacking `WATER BOTTLE`, `JUICE BOX`, `EMPTY CUP` at the kitchen counter).

---

## 3. Limitations & Future Roadmap

*   **What Breaks**:
    *   **Out-of-Typical-Location Items**: If an object is moved away from its predefined typical search room (e.g., placing the towel in the study), the agent's initial search heuristic will fail.
    *   **Exhaustive Search**: The agent does not yet implement a full-house flood-fill exploration algorithm to look through every single room if the item is not at its typical location.
*   **Future Enhancements**:
    *   **Heuristic Exploration Pathing**: Implement a backup search state where, if an item is not found at its typical location, the robot automatically generates a search path passing through all rooms systematically.
    *   **Structured Output Schema**: Enforce a strict JSON Schema configuration on the Gemini model object to guarantee syntactic structure without relying on regex cleanups.
