from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import base64, io, httpx
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor, black, white
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os, math

app = FastAPI()

# Register DejaVu fonts for Cyrillic support
FONT_DIR = "/usr/share/fonts/truetype/dejavu"
try:
    pdfmetrics.registerFont(TTFont("DejaVu", f"{FONT_DIR}/DejaVuSans.ttf"))
    pdfmetrics.registerFont(TTFont("DejaVuBold", f"{FONT_DIR}/DejaVuSans-Bold.ttf"))
    FONT_NAME = "DejaVu"
    FONT_BOLD = "DejaVuBold"
except Exception:
    FONT_NAME = "Helvetica"
    FONT_BOLD = "Helvetica-Bold"


class LetterRequest(BaseModel):
    text: str
    entity_name: str = "ИП Лапшенков"
    date: str = ""
    seal: bool = True


class SendLetterRequest(BaseModel):
    text: str
    entity_name: str = "ИП Лапшенков"
    date: str = ""
    seal: bool = True
    chat_id: str
    bot_token: str
    caption: str = ""


def draw_letter(buffer: io.BytesIO, req: LetterRequest) -> None:
    W, H = A4
    c = canvas.Canvas(buffer, pagesize=A4)

    DARK = HexColor("#2c3e50")
    GREY = HexColor("#7f8c8d")
    LIGHT = HexColor("#bdc3c7")
    margin_l = 3 * cm
    margin_r = 2 * cm
    text_width = W - margin_l - margin_r

    y = H - 2 * cm

    # ── Header: company name ──
    c.setFillColor(DARK)
    c.setFont(FONT_BOLD, 16)
    name = req.entity_name.upper()
    name_w = c.stringWidth(name, FONT_BOLD, 16)
    c.drawString((W - name_w) / 2, y, name)
    y -= 0.5 * cm

    c.setFont(FONT_NAME, 8)
    c.setFillColor(GREY)
    tagline = "GoodSupport  ·  Официальное письмо"
    tg_w = c.stringWidth(tagline, FONT_NAME, 8)
    c.drawString((W - tg_w) / 2, y, tagline)
    y -= 0.35 * cm

    # Divider line
    c.setStrokeColor(DARK)
    c.setLineWidth(1.5)
    c.line(margin_l, y, W - margin_r, y)
    y -= 0.8 * cm

    # ── Date ──
    if req.date:
        c.setFont(FONT_NAME, 10)
        c.setFillColor(GREY)
        date_w = c.stringWidth(req.date, FONT_NAME, 10)
        c.drawString(W - margin_r - date_w, y, req.date)
        y -= 0.8 * cm

    # ── Letter body ──
    c.setFont(FONT_NAME, 11.5)
    c.setFillColor(black)
    line_h = 0.62 * cm
    bottom_margin = 5 * cm

    for raw_line in req.text.split("\n"):
        words = raw_line.split(" ") if raw_line.strip() else [""]
        current = ""
        for word in words:
            test = (current + " " + word).strip()
            if c.stringWidth(test, FONT_NAME, 11.5) <= text_width:
                current = test
            else:
                if y < bottom_margin:
                    c.showPage()
                    y = H - 2 * cm
                    c.setFont(FONT_NAME, 11.5)
                    c.setFillColor(black)
                c.drawString(margin_l, y, current)
                y -= line_h
                current = word
        if y < bottom_margin:
            c.showPage()
            y = H - 2 * cm
            c.setFont(FONT_NAME, 11.5)
            c.setFillColor(black)
        c.drawString(margin_l, y, current)
        y -= line_h

    # ── Footer divider ──
    footer_y = 3.5 * cm
    c.setStrokeColor(LIGHT)
    c.setLineWidth(0.8)
    c.line(margin_l, footer_y, W - margin_r, footer_y)

    # ── Seal circle ──
    if req.seal:
        seal_cx = W - margin_r - 2 * cm
        seal_cy = footer_y - 1.5 * cm
        seal_r = 1.5 * cm

        c.setStrokeColor(DARK)
        c.setFillColor(white)
        c.setLineWidth(2)
        c.circle(seal_cx, seal_cy, seal_r, stroke=1, fill=1)

        c.setFillColor(DARK)
        c.setFont(FONT_BOLD, 7)
        short = req.entity_name.replace("ООО ", "").replace("ИП ", "")[:12]
        lines_seal = ["М.П.", "ПЕЧАТЬ", short]
        for i, sl in enumerate(lines_seal):
            sw = c.stringWidth(sl, FONT_BOLD, 7)
            c.drawString(seal_cx - sw / 2, seal_cy + 0.3 * cm - i * 0.45 * cm, sl)

    c.save()


@app.post("/generate")
async def generate_pdf(req: LetterRequest):
    buf = io.BytesIO()
    draw_letter(buf, req)
    pdf_bytes = buf.getvalue()
    return JSONResponse({"pdf_base64": base64.b64encode(pdf_bytes).decode()})


@app.post("/send")
async def send_letter(req: SendLetterRequest):
    """Generate PDF and send directly to Telegram — bypasses n8n binary upload issues."""
    buf = io.BytesIO()
    draw_letter(buf, LetterRequest(
        text=req.text,
        entity_name=req.entity_name,
        date=req.date,
        seal=req.seal
    ))
    pdf_bytes = buf.getvalue()

    fname = f"Письмо_{datetime.now().strftime('%Y-%m-%d')}.pdf"
    caption = req.caption or f"📄 Письмо — {req.entity_name}"

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{req.bot_token}/sendDocument",
            data={"chat_id": req.chat_id, "caption": caption},
            files={"document": (fname, pdf_bytes, "application/pdf")}
        )

    result = resp.json()
    if result.get("ok"):
        return {"success": True}
    else:
        return JSONResponse(
            {"success": False, "error": result.get("description", "Telegram error")},
            status_code=500
        )


@app.get("/health")
async def health():
    return {"status": "ok", "font": FONT_NAME}
