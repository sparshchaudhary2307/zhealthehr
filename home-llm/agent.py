import json
import os
import time
import sys
import builtins
import threading
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables with hardcoded fallback
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
else:
    print("Warning: GEMINI_API_KEY is not set. Generative AI features will not work.")

# Monkey-patch builtins.input to poll Pygame events on the main thread while waiting for terminal input
original_input = builtins.input

def non_blocking_input(prompt=""):
    try:
        import pygame
        if pygame.get_init() and pygame.display.get_init():
            # Print prompt
            print(prompt, end="", flush=True)
            
            # Read from stdin in a background thread
            user_input = [None]
            def read_stdin():
                try:
                    user_input[0] = sys.stdin.readline()
                except Exception:
                    pass
            
            t = threading.Thread(target=read_stdin, daemon=True)
            t.start()
            
            # Poll Pygame events on the main thread while waiting
            while t.is_alive():
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        pygame.quit()
                        sys.exit()
                time.sleep(0.05)
                
            if user_input[0] is not None:
                return user_input[0].rstrip("\r\n")
            return ""
    except Exception:
        pass
    return original_input(prompt)

builtins.input = non_blocking_input

SYSTEM_INSTRUCTIONS = """You are the brain of a simulated home robot. 
Your goal is to complete the user's request safely, sensibly, and while grounding your actions in what you have actually verified.

Capabilities:
- navigate_to(location): Move to a location. Senses all objects at that location upon arrival.
- pick(object): Pick up an object. You must be at the object's current location and holding nothing else. Note: Gripper slips sometimes (30% failure rate).
- place(location): Place the held object at the current location.
- speak(text): Speak to the person.

Valid Locations:
{known_locations}

Predefined world objects have typical locations:
- water_bottle, juice_box, empty_cup, kitchen_knife: kitchen_counter
- tv_remote, newspaper: dining_table
- pill_bottle, eyeglasses: bedside_table
- book: desk
- towel: bathroom

Rule 1: Grounding
You cannot pick or interact with an object unless it is in your `known_objects` list.
If a requested object is NOT in the `known_objects` list, you must first navigate to its typical location (or rooms it might be in) to sense/verify it.
If an object is not in the house or cannot be found after searching typical locations, speak to the user explaining you cannot find it, then stop. Do not guess or act on unverified objects.

Rule 2: Safety
Never touch or pick up unsafe objects:
- UNSAFE: "kitchen_knife", "pill_bottle". If asked to handle these, politely refuse using the `speak` action and stop.
- SAFE: "water_bottle", "juice_box", "empty_cup", "tv_remote", "newspaper", "book", "towel", "eyeglasses". You should handle these normally.

Rule 3: Ambiguity
If the user's request is ambiguous (e.g., "get me something to drink" when there is both water_bottle and juice_box, or "bring me the book" if you had multiple, or "bring something to read" when newspaper and book exist), ask a clarifying question using `speak` and stop. Do not guess.

Rule 4: Chit-chat / Out-of-Scope
If the request is simple chit-chat (e.g., "What can you do?") or completely out of scope (e.g., "open the window"), use the `speak` action to respond or explain your limitations, and then stop.

Rule 5: Recovery
If a previous action (like pick) failed (e.g., "Grasp of '...' slipped"), retry the action or find a way to recover.

Rule 6: User Location ("me") vs. Named Locations
- If the user specifies a named location (e.g., "bedroom", "living_room", "study", "kitchen", "dining_table", "bedside_table", "desk", "bathroom"), always use that specific location as the target destination.
- Only if the destination is unspecified or generic (e.g., "bring me", "get me", "bring it to me"), you should bring it to the user's starting location (`starting_location` provided in state_info).

Rule 7: Communication and Termination
- After using the `speak` action to ask a clarifying question, refuse a request, or answer chit-chat/out-of-scope requests, you must set action to "done" in the very next turn.
- When you successfully complete a task (such as placing the requested object at the destination), use the `speak` action to politely notify the user (e.g., "I have brought the book to the hallway.") before declaring you are "done" in the next turn.

Output Format:
You must respond with a JSON object containing:
{{
  "thought": "Your step-by-step reasoning",
  "action": "one of: navigate_to | pick | place | speak | done",
  "arg": "the argument for the action (e.g., location name, object name, speech text, or empty string)"
}}
"""

def call_llm(system, user):
    model = genai.GenerativeModel(
        model_name="gemini-3.1-flash-lite",
        generation_config={"response_mime_type": "application/json"}
    )
    
    max_retries = 6
    backoff = 10.0
    for attempt in range(max_retries):
        try:
            response = model.generate_content(
                contents=[
                    {"role": "user", "parts": [system + "\n\nUser request/state:\n" + user]}
                ]
            )
            return response.text
        except Exception as e:
            err_str = str(e)
            print(f"API Call failed (attempt {attempt+1}/{max_retries}): {err_str}")
            if "429" in err_str or "quota" in err_str.lower() or "ResourceExhausted" in err_str:
                print(f"Rate limit / quota hit. Sleeping {backoff} seconds before retry...")
                time.sleep(backoff)
                backoff *= 1.5
                continue
            time.sleep(2)
            
    # Fallback to simple JSON in case of persistent failure
    return json.dumps({"thought": "API call failed after retries", "action": "speak", "arg": "I am having trouble connecting to my brain."})


class Agent:
    def __init__(self, robot):
        self.robot = robot
        
        # Intercept and wrap Pygame renderer to show room names and all item placements
        if robot._renderer is not None:
            original_render = robot._renderer
            closure_dict = {}
            if hasattr(original_render, "__closure__") and original_render.__closure__:
                for var, cell in zip(original_render.__code__.co_freevars, original_render.__closure__):
                    closure_dict[var] = cell.cell_contents
            
            screen = closure_dict.get("screen")
            cell = closure_dict.get("cell", 22)
            font = closure_dict.get("font")
            bigfont = closure_dict.get("bigfont")
            
            def enhanced_render(r, transient=None):
                import pygame
                import sys
                from home_robot_sim import GRID, GRID_W, GRID_H, ROOMS, LOCATIONS
                
                # Check for Pygame close window event
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        pygame.quit()
                        sys.exit()
                
                nonlocal screen, cell, font, bigfont
                if not screen:
                    screen = pygame.display.get_surface()
                if not font:
                    font = pygame.font.SysFont("monospace", 12)
                if not bigfont:
                    bigfont = pygame.font.SysFont("monospace", 16)
                
                # Draw background grid
                screen.fill((25, 25, 30))
                for y in range(GRID_H):
                    for x in range(GRID_W):
                        rect = pygame.Rect(x * cell, y * cell, cell - 1, cell - 1)
                        color = (40, 40, 50) if GRID[y][x] else (235, 235, 240)
                        pygame.draw.rect(screen, color, rect)
                
                # Draw room boundaries and room names (center-aligned in room)
                for room_name, coords in ROOMS.items():
                    x0, y0, x1, y1 = coords
                    cx = (x0 + x1) / 2
                    cy = (y0 + y1) / 2
                    txt = font.render(room_name.upper().replace("_", " "), True, (130, 130, 160))
                    text_rect = txt.get_rect(center=(cx * cell + cell // 2, cy * cell + cell // 2))
                    screen.blit(txt, text_rect)
                
                # Draw target location markers (furniture dots and labels)
                for loc_name, pos in LOCATIONS.items():
                    lx, ly = pos
                    pygame.draw.circle(screen, (160, 160, 180),
                                       (lx * cell + cell // 2, ly * cell + cell // 2), 4)
                    # Only draw the label if it's not a generic room name to prevent duplicate text overlaps
                    if loc_name not in ROOMS:
                        txt = font.render(loc_name.upper().replace("_", " "), True, (100, 100, 120))
                        screen.blit(txt, (lx * cell - 10, ly * cell + 6))
                
                # Group items by location to prevent overlapping text at the same counter/table
                from collections import defaultdict
                loc_to_items = defaultdict(list)
                for obj_name, obj in r._objects.items():
                    if r.holding == obj_name:
                        continue
                    loc_to_items[obj.location].append(obj_name)
                
                # Draw items stacked vertically at their respective locations
                for loc_name, items in loc_to_items.items():
                    if loc_name in LOCATIONS:
                        lx, ly = LOCATIONS[loc_name]
                        # Draw a clear green circle for the items
                        pygame.draw.circle(screen, (50, 180, 100),
                                           (lx * cell + cell // 2, ly * cell + cell // 2), cell // 3)
                        # Render item names stacked vertically above the circle
                        for idx, item_name in enumerate(items):
                            txt = font.render(item_name.upper().replace("_", " "), True, (30, 100, 50))
                            screen.blit(txt, (lx * cell - 6, ly * cell - 14 - (idx * 11)))
                
                # Draw the robot
                rx, ry = r._pos
                pygame.draw.circle(screen, (40, 110, 230),
                                   (rx * cell + cell // 2, ry * cell + cell // 2), cell // 2)
                txt = bigfont.render("R", True, (255, 255, 255))
                text_rect = txt.get_rect(center=(rx * cell + cell // 2, ry * cell + cell // 2))
                screen.blit(txt, text_rect)
                
                # Draw status/speech text at the bottom panel
                y0 = GRID_H * cell + 6
                screen.blit(font.render(f"loc={r.current_location}  holding={r.holding}",
                                        True, (230, 230, 230)), (8, y0))
                screen.blit(font.render(f"known={list(r.known_objects)}",
                                        True, (200, 200, 200)), (8, y0 + 18))
                if r._last_speech:
                    screen.blit(bigfont.render(f'SAYS: "{r._last_speech}"',
                                               True, (250, 220, 120)), (8, y0 + 40))
                
                pygame.display.flip()
                
            robot._renderer = enhanced_render

    def handle(self, command):
        system = SYSTEM_INSTRUCTIONS.format(known_locations=self.robot.known_locations)
        history = []
        starting_location = self.robot.current_location
        
        for step in range(15):
            # Format current state
            state_info = {
                "user_command": command,
                "starting_location": starting_location,
                "current_location": self.robot.current_location,
                "holding": self.robot.holding,
                "known_objects": self.robot.known_objects,
                "history_of_this_command": history
            }
            
            raw_response = call_llm(system, json.dumps(state_info, indent=2))
            
            try:
                data = json.loads(raw_response)
            except Exception:
                # Clean up any potential markdown fences
                cleaned = raw_response.strip()
                if cleaned.startswith("```json"):
                    cleaned = cleaned[7:]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
                try:
                    data = json.loads(cleaned.strip())
                except Exception:
                    self.robot.speak("Sorry, I got confused while planning.")
                    break
            
            action = data.get("action")
            arg = data.get("arg")
            thought = data.get("thought", "")
            
            print(f"Thought: {thought}")
            print(f"Action: {action}({arg})")
            
            if action == "done":
                break
                
            if action == "speak":
                self.robot.speak(arg)
                history.append(f"Action: speak('{arg}') -> Success")
                continue
                
            fn = getattr(self.robot, action, None)
            if fn is None:
                history.append(f"Action: {action}('{arg}') -> Failed: Invalid action")
                continue
                
            result = fn(arg)
            print("   ", result)
            history.append(f"Action: {action}('{arg}') -> Result: {result}")
