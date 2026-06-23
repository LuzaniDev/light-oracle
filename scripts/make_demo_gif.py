"""Gera um GIF do sistema Oracle RAG"""
import sys, os, time, subprocess, shutil, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.sync_api import sync_playwright
from PIL import Image

OUTPUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "demo.gif")
TEMP = tempfile.mkdtemp()

print("Iniciando servidor...")
server = subprocess.Popen(
    [sys.executable, "run_web.py"],
    cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
)
time.sleep(20)

frames = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 720})

    page.goto("http://localhost:8081", timeout=30000)
    page.wait_for_timeout(3000)
    frames.append(os.path.join(TEMP, "1.png"))
    page.screenshot(path=frames[-1])

    page.fill('input[placeholder*="pergunta"]', "Exemplo de pergunta")
    page.wait_for_timeout(1000)
    frames.append(os.path.join(TEMP, "2.png"))
    page.screenshot(path=frames[-1])

    page.click('button:has-text("Enviar")')
    page.wait_for_timeout(10000)
    frames.append(os.path.join(TEMP, "3.png"))
    page.screenshot(path=frames[-1])
    page.wait_for_timeout(3000)
    frames.append(os.path.join(TEMP, "4.png"))
    page.screenshot(path=frames[-1])

    browser.close()

server.terminate()

os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
pil_frames = [Image.open(f) for f in frames]
pil_frames[0].save(OUTPUT, save_all=True, append_images=pil_frames[1:], duration=2000, loop=0)
shutil.rmtree(TEMP, ignore_errors=True)
print(f"GIF criado: {OUTPUT} ({len(frames)} frames)")
