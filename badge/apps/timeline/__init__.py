import sys
import os

sys.path.insert(0, "/system/apps/timeline")
os.chdir("/system/apps/timeline")

"""
Timeline App - GitHub Contribution Viewer

Controls:
- A: Scroll left through contributions
- C: Scroll right through contributions  
- B: Refresh GitHub data (re-fetch from API)
"""

from badgeware import io, brushes, shapes, Image, run, PixelFont, screen, Matrix, file_exists
import random
import math
import network
from urllib.urequest import urlopen
import gc
import sys
import json


phosphor = brushes.color(211, 250, 55, 150)
white = brushes.color(235, 245, 255)
faded = brushes.color(235, 245, 255, 100)
small_font = PixelFont.load("/system/assets/fonts/ark.ppf")
large_font = PixelFont.load("/system/assets/fonts/absolute.ppf")

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
WIFI_TIMEOUT = 60
CONTRIB_URL = "https://github.com/{user}.contribs"
USER_AVATAR = "https://wsrv.nl/?url=https://github.com/{user}.png&w=40&output=png"
DETAILS_URL = "https://api.github.com/users/{user}"

WIFI_PASSWORD = None
WIFI_SSID = None

wlan = None
connected = False
ticks_start = None


def message(text):
    print(text)


def get_connection_details(user):
    global WIFI_PASSWORD, WIFI_SSID

    if WIFI_SSID is not None and user.handle is not None:
        return True

    try:
        sys.path.insert(0, "/")
        from secrets import WIFI_PASSWORD, WIFI_SSID, GITHUB_USERNAME
        sys.path.pop(0)
    except ImportError:
        WIFI_PASSWORD = None
        WIFI_SSID = None
        GITHUB_USERNAME = None

    if not WIFI_SSID:
        return False

    if not GITHUB_USERNAME:
        return False

    user.handle = GITHUB_USERNAME

    return True


def wlan_start():
    global wlan, ticks_start, connected, WIFI_PASSWORD, WIFI_SSID

    if ticks_start is None:
        ticks_start = io.ticks

    if connected:
        return True

    if wlan is None:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)

        if wlan.isconnected():
            return True

    # attempt to find the SSID by scanning; some APs may be hidden intermittently
    try:
        ssid_found = False
        try:
            scans = wlan.scan()
        except Exception:
            scans = []

        for s in scans:
            # s[0] is SSID (bytes or str)
            ss = s[0]
            if isinstance(ss, (bytes, bytearray)):
                try:
                    ss = ss.decode("utf-8", "ignore")
                except Exception:
                    ss = str(ss)
            if ss == WIFI_SSID:
                ssid_found = True
                break

        if not ssid_found:
            # not found yet; if still within timeout, keep trying on subsequent calls
            if io.ticks - ticks_start < WIFI_TIMEOUT * 1000:
                # optionally print once every few seconds to avoid spamming
                if (io.ticks - ticks_start) % 3000 < 50:
                    print("SSID not visible yet; rescanning...")
                # return True to indicate we're still attempting to connect (in-progress)
                return True
            else:
                # timed out
                return False

        # SSID is visible; attempt to connect (or re-attempt)
        try:
            wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        except Exception:
            # connection initiation failed; we'll retry while still within timeout
            if io.ticks - ticks_start < WIFI_TIMEOUT * 1000:
                return True
            return False

        print("Connecting to WiFi...")

        # update connected state
        connected = wlan.isconnected()

        # if connected, return True; otherwise indicate in-progress until timeout
        if connected:
            return True
        if io.ticks - ticks_start < WIFI_TIMEOUT * 1000:
            return True
        return False
    except Exception as e:
        # on unexpected errors, don't crash the UI; report and return False
        try:
            print("wlan_start error:", e)
        except Exception:
            pass
        return False


def async_fetch_to_disk(url, file, force_update=False):
    if not force_update and file_exists(file):
        return
    try:
        # Grab the data
        response = urlopen(url, headers={"User-Agent": "GitHub Universe Badge 2025"})
        data = bytearray(512)
        total = 0
        with open(file, "wb") as f:
            while True:
                if (length := response.readinto(data)) == 0:
                    break
                total += length
                message(f"Fetched {total} bytes")
                f.write(data[:length])
                yield
        del data
        del response
    except Exception as e:
        raise RuntimeError(f"Fetch from {url} to {file} failed. {e}") from e


def get_user_data(user, force_update=False):
    message(f"Getting user data for {user.handle}...")
    yield from async_fetch_to_disk(DETAILS_URL.format(user=user.handle), "/user_data.json", force_update)
    r = json.loads(open("/user_data.json", "r").read())
    user.name = r["name"]
    user.handle = r["login"]
    user.followers = r["followers"]
    user.repos = r["public_repos"]
    user.location = r.get("location", "")
    del r
    gc.collect()


def get_contrib_data(user, force_update=False):
    message(f"Getting contribution data for {user.handle}...")
    yield from async_fetch_to_disk(CONTRIB_URL.format(user=user.handle), "/contrib_data.json", force_update)
    r = json.loads(open("/contrib_data.json", "r").read())
    user.contribs = r["total_contributions"]
    # Store full year (53 weeks)
    user.contribution_data = [[0 for _ in range(53)] for _ in range(7)]
    weeks = r["weeks"]
    # Get the full year of data (up to 53 weeks)
    for w_idx, week in enumerate(weeks):
        if w_idx >= 53:
            break
        for day in range(7):
            try:
                user.contribution_data[day][w_idx] = week["contribution_days"][day]["level"]
            except (IndexError, KeyError):
                pass
    
    # Extract start and end dates from top-level fields
    try:
        user.start_date = r.get("from")
        user.end_date = r.get("to")
    except (KeyError, AttributeError):
        user.start_date = None
        user.end_date = None
    
    del r
    gc.collect()


def get_avatar(user, force_update=False):
    message(f"Getting avatar for {user.handle}...")
    yield from async_fetch_to_disk(USER_AVATAR.format(user=user.handle), "/avatar.png", force_update)
    user.avatar = Image.load("/avatar.png")


def fake_number():
    return random.randint(10000, 99999)


def placeholder_if_none(text):
    if text:
        return text
    old_seed = random.seed()
    random.seed(int(io.ticks / 100))
    chars = "!\"£$%^&*()_+-={}[]:@~;'#<>?,./\\|"
    text = ""
    for _ in range(20):
        text += random.choice(chars)
    random.seed(old_seed)
    return text


class User:
    levels = [
        brushes.color(21,  27,  35),      # Level 0 - dark background (slightly brighter)
        brushes.color(40, 140,  70),      # Level 1 - brighter green (was 25/2, 108/2, 46/2)
        brushes.color(70, 200, 100),      # Level 2 - bright green (was 46/2, 160/2, 67/2)
        brushes.color(110, 240, 130),     # Level 3 - very bright green (was 86/2, 211/2, 100/2)
        brushes.color(150, 255, 170),     # Level 4 - maximum brightness green (was 120/2, 255/2, 140/2)
    ]

    def __init__(self):
        self.handle = None
        self.update(force_update=True)

    def update(self, force_update=False):
        self.name = None
        self.contribs = None
        self.contribution_data = None
        self.avatar = None
        self.location = None
        self.start_date = None
        self.end_date = None
        self._task = None
        self._force_update = force_update

    def draw_stat(self, title, value, x, y):
        screen.brush = white if value else faded
        screen.font = small_font  # Changed from large_font for consistency
        screen.text(str(value) if value is not None else str(fake_number()), x, y)
        screen.font = small_font
        screen.brush = phosphor
        screen.text(title, x - 1, y + 10)  # Reduced from y + 13 since value is now smaller

    def draw(self, connected, scroll_offset):
        # draw handle
        screen.font = large_font
        handle = self.handle

        # use the handle area to show loading progress if not everything is ready
        if (not self.handle or not self.avatar or not self.contribs) and connected:
            if not self.name:
                handle = "fetching user data..."
                if not self._task:
                    self._task = get_user_data(self, self._force_update)
            elif not self.contribs:
                handle = "fetching contribs..."
                if not self._task:
                    self._task = get_contrib_data(self, self._force_update)
            else:
                handle = "fetching avatar..."
                if not self._task:
                    self._task = get_avatar(self, self._force_update)

            try:
                next(self._task)
            except StopIteration:
                self._task = None
            except:
                self._task = None
                handle = "fetch error"

        if not connected:
            handle = "connecting..."

        # draw smaller avatar image, aligned with user info
        avatar_x = 5  # Reduced from 10 to push avatar to the left
        avatar_size = 40  # Smaller avatar size (was 75)
        # Avatar top aligns with username, bottom aligns with contributions label
        # After alignment, all elements are moved down 5 pixels together
        avatar_y = 8  # Aligned with username position (3 + 5 pixels down)
        avatar_center = avatar_size // 2  # Center point for loading animation
        
        if not self.avatar:
            # create a spinning loading animation while we wait for the avatar to load
            screen.brush = phosphor
            squircle = shapes.squircle(0, 0, 10, 5)
            screen.brush = brushes.color(211, 250, 55, 50)
            for i in range(4):
                mul = math.sin(io.ticks / 1000) * 14000
                squircle.transform = Matrix().translate(
                    avatar_x + avatar_center, avatar_y + avatar_center
                ).rotate((io.ticks + i * mul) / 40).scale(1 + i / 1.3)
                screen.draw(squircle)
        else:
            screen.blit(self.avatar, avatar_x, avatar_y)

        # draw handle to the right of the avatar, prefixed with "@"
        screen.font = small_font  # Changed from large_font to reduce username size
        screen.brush = white
        handle_x = avatar_x + avatar_size + 5  # Reduced margin from 10 to 5 to give username more room
        handle_y = 8  # Aligned with top of profile picture (3 + 5 pixels down)
        # Truncate username if it's too long to fit on screen
        handle_text = "@" + handle
        max_width = 160 - handle_x - 2  # Leave 2px margin on right
        text_width, _ = screen.measure_text(handle_text)
        if text_width > max_width:
            # Truncate and add ellipsis - measure ellipsis once
            ellipsis_width, _ = screen.measure_text("...")
            available_width = max_width - ellipsis_width
            while len(handle_text) > 2:
                handle_text = handle_text[:-1]
                text_width, _ = screen.measure_text(handle_text)
                if text_width <= available_width:
                    break
            handle_text = handle_text + "..."
        screen.text(handle_text, handle_x, handle_y)

        # draw location below username (replacing name)
        screen.font = small_font
        screen.brush = phosphor
        location = placeholder_if_none(self.location) or "Unknown"
        screen.text(location, handle_x, handle_y + 10)  # Reduced gap from 14 to 10

        # draw contributions statistic below location
        self.draw_stat("contributions", self.contribs, handle_x, handle_y + 22)  # Changed from "commits" to "contributions"

        # draw contribution graph below the profile section - horizontal scrolling layout
        size = 5  # Square size
        weeks = 53  # Show full year (53 weeks)
        days_per_week = 7
        # Position below the avatar/profile section with reduced padding
        x_offset = 5
        y_offset = 60  # Moved down 10 pixels from 50
        
        # Calculate visible area
        visible_width = 160 - x_offset * 2  # Screen width minus margins
        max_scroll = max(0, weeks * (size + 2) - visible_width)
        
        screen.font = small_font
        rect = shapes.rounded_rectangle(0, 0, size, size, 2)
        for week in range(weeks):
            # Calculate x position considering scroll offset
            week_x = x_offset + week * (size + 2) - scroll_offset
            # Only draw if visible on screen
            if week_x + size >= 0 and week_x < 160:
                for day in range(days_per_week):
                    if (self.contribution_data and 
                        day < len(self.contribution_data) and 
                        week < len(self.contribution_data[0])):
                        level = self.contribution_data[day][week]
                        screen.brush = User.levels[level]
                    else:
                        screen.brush = User.levels[0]
                    # Horizontal layout: weeks are columns (x), days are rows (y)
                    pos = (week_x, y_offset + day * (size + 2))
                    rect.transform = Matrix().translate(*pos)
                    screen.draw(rect)
        
        # Draw start and end dates as "Month Year - Month Year" centered at bottom
        screen.brush = white
        screen.font = small_font
        if self.start_date and self.end_date:
            # Format dates from YYYY-MM-DD to "Month Year"
            try:
                start_parts = self.start_date.split('-')
                start_month_idx = int(start_parts[1]) - 1
                # Validate month index
                if 0 <= start_month_idx < 12:
                    start_month = MONTHS[start_month_idx]
                    start_year = start_parts[0]
                else:
                    raise ValueError("Invalid month")
                
                end_parts = self.end_date.split('-')
                end_month_idx = int(end_parts[1]) - 1
                # Validate month index
                if 0 <= end_month_idx < 12:
                    end_month = MONTHS[end_month_idx]
                    end_year = end_parts[0]
                else:
                    raise ValueError("Invalid month")
                
                # Create centered text "Month Year - Month Year"
                date_text = f"{start_month} {start_year} - {end_month} {end_year}"
                text_width, _ = screen.measure_text(date_text)
                text_x = (160 - text_width) // 2  # Center horizontally
                text_y = y_offset + days_per_week * (size + 2)  # Moved up 2 pixels
                screen.text(date_text, text_x, text_y)
            except (IndexError, ValueError):
                pass


user = User()
connected = False
force_update = False

# Scrolling state
scroll_offset = 0
scroll_speed = 0.5  # pixels per frame
scroll_direction = 1  # 1 for right, -1 for left
last_input_time = 0
auto_scroll_enabled = True
INPUT_TIMEOUT = 10000  # 10 seconds in milliseconds


def center_text(text, y):
  w, h = screen.measure_text(text)
  screen.text(text, 80 - (w / 2), y)


def wrap_text(text, x, y):
  lines = text.splitlines()
  for line in lines:
    _, h = screen.measure_text(line)
    screen.text(line, x, y)
    y += h * 0.8


# tell the user where to fill in their details
def no_secrets_error():
  screen.font = large_font
  screen.brush = white
  center_text("Missing Details!", 5)

  screen.text("1:", 10, 23)
  screen.text("2:", 10, 55)
  screen.text("3:", 10, 87)

  screen.brush = phosphor
  screen.font = small_font
  wrap_text("""Put your badge into\ndisk mode (tap\nRESET twice)""", 30, 24)

  wrap_text("""Edit 'secrets.py' to\nset WiFi details and\nGitHub username.""", 30, 56)

  wrap_text("""Reload to see your\nsweet sweet stats!""", 30, 88)


# tell the user that the connection failed :-(
def connection_error():
  screen.font = large_font
  screen.brush = white
  center_text("Connection Failed!", 5)

  screen.text("1:", 10, 63)
  screen.text("2:", 10, 95)

  screen.brush = phosphor
  screen.font = small_font
  wrap_text("""Could not connect\nto the WiFi network.\n\n:-(""", 16, 20)

  wrap_text("""Edit 'secrets.py' to\nset WiFi details and\nGitHub username.""", 30, 65)

  wrap_text("""Reload to see your\nsweet sweet stats!""", 30, 96)


def update():
    global connected, force_update, scroll_offset, scroll_direction, last_input_time, auto_scroll_enabled

    # Use a dark blue-gray background that complements the contribution colors
    screen.brush = brushes.color(13, 17, 23)
    screen.draw(shapes.rectangle(0, 0, 160, 120))

    force_update = False

    # Handle B button for refreshing data
    if io.BUTTON_B in io.pressed:
        connected = False
        user.update(True)

    # Calculate max scroll based on contribution data
    size = 5
    weeks = 53
    x_offset = 5
    visible_width = 160 - x_offset * 2
    max_scroll = max(0, weeks * (size + 2) - visible_width)
    
    # Handle manual scrolling with A and C buttons
    if io.BUTTON_A in io.pressed or io.BUTTON_C in io.pressed:
        last_input_time = io.ticks
        auto_scroll_enabled = False
        
        if io.BUTTON_A in io.pressed:
            # Scroll left
            scroll_offset = max(0, scroll_offset - 10)
        elif io.BUTTON_C in io.pressed:
            # Scroll right
            scroll_offset = min(max_scroll, scroll_offset + 10)
    
    # Re-enable auto-scroll after timeout
    if not auto_scroll_enabled and (io.ticks - last_input_time > INPUT_TIMEOUT):
        auto_scroll_enabled = True
    
    # Auto-scroll logic
    if auto_scroll_enabled:
        scroll_offset += scroll_speed * scroll_direction
        
        # Bounce at edges
        if scroll_offset >= max_scroll:
            scroll_offset = max_scroll
            scroll_direction = -1  # Reverse to left
        elif scroll_offset <= 0:
            scroll_offset = 0
            scroll_direction = 1  # Reverse to right

    if get_connection_details(user):
        if wlan_start():
            user.draw(connected, scroll_offset)
        else:  # Connection Failed
            connection_error()
    else:      # Get Details Failed
        no_secrets_error()


if __name__ == "__main__":
    run(update)
