import sys
import os

sys.path.insert(0, "/system/apps/timeline")
os.chdir("/system/apps/timeline")


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

WIFI_TIMEOUT = 60
CONTRIB_URL = "https://github.com/{user}.contribs"
USER_AVATAR = "https://wsrv.nl/?url=https://github.com/{user}.png&w=75&output=png"
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
    del r
    gc.collect()


def get_contrib_data(user, force_update=False):
    message(f"Getting contribution data for {user.handle}...")
    yield from async_fetch_to_disk(CONTRIB_URL.format(user=user.handle), "/contrib_data.json", force_update)
    r = json.loads(open("/contrib_data.json", "r").read())
    user.contribs = r["total_contributions"]
    # Only store last 2 weeks (14 days)
    user.contribution_data = [[0 for _ in range(14)] for _ in range(7)]
    # Get the last 2 weeks of data
    weeks = r["weeks"]
    start_week = max(0, len(weeks) - 2)  # Start from 2 weeks ago
    for w_idx, week in enumerate(weeks[start_week:]):
        for day in range(7):
            try:
                user.contribution_data[day][w_idx] = week["contribution_days"][day]["level"]
            except (IndexError, KeyError):
                pass
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
        brushes.color(21 / 2,  27 / 2,  35 / 2),
        brushes.color(3 / 2,  58 / 2,  22 / 2),
        brushes.color(25 / 2, 108 / 2,  46 / 2),
        brushes.color(46 / 2, 160 / 2,  67 / 2),
        brushes.color(86 / 2, 211 / 2, 100 / 2),
    ]

    def __init__(self):
        self.handle = None
        self.update()

    def update(self, force_update=False):
        self.name = None
        self.contribs = None
        self.contribution_data = None
        self.avatar = None
        self._task = None
        self._force_update = force_update

    def draw_stat(self, title, value, x, y):
        screen.brush = white if value else faded
        screen.font = large_font
        screen.text(str(value) if value is not None else str(fake_number()), x, y)
        screen.font = small_font
        screen.brush = phosphor
        screen.text(title, x - 1, y + 13)

    def draw(self, connected):
        # draw contribution graph at the bottom - horizontal layout
        size = 8  # Smaller size to fit days horizontally
        weeks = 2  # Show 2 weeks
        days_per_week = 7
        # Calculate heatmap dimensions (days as columns, weeks as rows)
        graph_width = days_per_week * (size + 2)
        graph_height = weeks * (size + 2)
        # Center the heatmap horizontally
        x_offset = (160 - graph_width) // 2
        # Position at bottom of screen
        y_offset = 120 - graph_height - 2

        screen.font = small_font
        rect = shapes.rounded_rectangle(0, 0, size, size, 2)
        for week in range(weeks):
            for day in range(days_per_week):
                if (self.contribution_data and 
                    day < len(self.contribution_data) and 
                    week < len(self.contribution_data[0])):
                    level = self.contribution_data[day][week]
                    screen.brush = User.levels[level]
                else:
                    screen.brush = User.levels[0]
                pos = (x_offset + day * (size + 2), y_offset + week * (size + 2))
                rect.transform = Matrix().translate(*pos)
                screen.draw(rect)

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

        # draw avatar image at the top left
        avatar_x = 5
        avatar_y = 5
        avatar_size = 75  # Avatar image is 75x75 pixels
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

        # draw handle to the right of the avatar
        screen.font = large_font
        screen.brush = white
        handle_x = avatar_x + avatar_size + 5  # Position to the right of avatar with 5px margin
        handle_y = 10
        screen.text(handle, handle_x, handle_y)

        # draw name below handle
        screen.font = small_font
        screen.brush = phosphor
        name = placeholder_if_none(self.name)
        screen.text(name, handle_x, handle_y + 14)

        # draw commits statistic below the avatar area
        self.draw_stat("commits", self.contribs, 80 - 15, 50)


user = User()
connected = file_exists("/contrib_data.json") and file_exists("/user_data.json") and file_exists("/avatar.png")
force_update = False


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
    global connected, force_update

    screen.brush = brushes.color(0, 0, 0)
    screen.draw(shapes.rectangle(0, 0, 160, 120))

    force_update = False

    if io.BUTTON_A in io.held and io.BUTTON_C in io.held:
        connected = False
        user.update(True)

    if get_connection_details(user):
        if wlan_start():
            user.draw(connected)
        else:  # Connection Failed
            connection_error()
    else:      # Get Details Failed
        no_secrets_error()


if __name__ == "__main__":
    run(update)
