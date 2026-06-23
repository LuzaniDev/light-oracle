"""Gera um GIF do sistema Oracle RAG em funcionamento"""
import sys, os, time, subprocess, shutil, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.sync_api import sync_playwright
from PIL import Image

OUTPUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "demo.gif")
TEMP = tempfile.mkdtemp()

print("=== Gerando GIF ===")

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

    page.goto("http://localhost:8081")
    page.wait_for_timeout(3000)
    frames.append(page.screenshot())

    page.fill('input[placeholder*="pergunta"]', "Exemplo de pergunta")
    page.wait_for_timeout(1000)
    frames.append(page.screenshot())

    page.click('button:has-text("Enviar")')
    page.wait_for_timeout(8000)
    frames.append(page.screenshot())
    page.wait_for_timeout(3000)
    frames.append(page.screenshot())

    browser.close()

server.terminate()
os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
frames_pil = [Image.open(f) for f in frames]
frames_pil[0].save(OUTPUT, save_all=True, append_images=frames_pil[1:], duration=2000, loop=0)
shutil.rmtree(TEMP, ignore_errors=True)
print(f"GIF: {OUTPUT} ({len(frames)} frames)")
