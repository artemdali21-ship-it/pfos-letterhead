from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import base64, io, httpx, os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

app = FastAPI()

HERE = os.path.dirname(os.path.abspath(__file__))

# ── Fonts ──
FONT_REGULAR = "Helvetica"
FONT_BOLD    = "Helvetica-Bold"
FONT_ITALIC  = "Helvetica-Oblique"

for candidate_dir in ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/Library/Fonts"]:
    reg    = os.path.join(candidate_dir, "DejaVuSans.ttf")
    bold   = os.path.join(candidate_dir, "DejaVuSans-Bold.ttf")
    italic = os.path.join(candidate_dir, "DejaVuSans-Oblique.ttf")
    if os.path.exists(reg) and os.path.exists(bold):
        pdfmetrics.registerFont(TTFont("BrandSans",       reg))
        pdfmetrics.registerFont(TTFont("BrandSans-Bold",  bold))
        if os.path.exists(italic):
            pdfmetrics.registerFont(TTFont("BrandSans-Italic", italic))
        FONT_REGULAR = "BrandSans"
        FONT_BOLD    = "BrandSans-Bold"
        FONT_ITALIC  = "BrandSans-Italic" if os.path.exists(italic) else "BrandSans"
        break

# ── Colors ──
ORANGE = HexColor("#E97C3F")
INK    = HexColor("#1A1A1A")
MUTED  = HexColor("#666666")
GREY   = HexColor("#DDDDDD")

# ── Page margins ──
PAGE_W, PAGE_H = A4
M_LEFT   = 20 * mm
M_RIGHT  = 20 * mm
M_TOP    = 18 * mm
M_BOTTOM = 18 * mm

# ── Entity configs ──
ENTITIES = {
    "ip": {
        "name":         "ИП Лапшенков Сергей Владимирович",
        "inn":          "772781135013",
        "kpp":          None,
        "ogrnip":       "321774600475424",
        "ogrn_label":   "ОГРНИП",
        "addr":         "117628, г. Москва, ул. Знаменские Садки, д. 3, корп. 5, кв. 238",
        "contact":      "+7 905 709-02-88 · 5604975@mail.ru",
        "footer_left":  "Good Support · ИП Лапшенков С. В. · Москва",
        "signer":       "Индивидуальный предприниматель\nЛапшенков Сергей Владимирович",
        "brand":        "бренд Good Support",
        "seal":         os.path.join(HERE, "seal_lapshenkov.png"),
        "seal_w":       70 * mm,
        "seal_ar":      826 / 1140,
    },
    "smart4yu": {
        "name":         "ООО «СМАРТ4Ю»",
        "inn":          "7709448483",
        "kpp":          "770901001",
        "ogrnip":       "1157746089929",
        "ogrn_label":   "ОГРН",
        "addr":         "109028, г. Москва, Хохловский пер., д. 15, помещ. 1В/П",
        "contact":      "Сбербанк · р/с 40702810238000248725 · БИК 044525225",
        "footer_left":  "Good Support · ООО «СМАРТ4Ю» · Москва",
        "signer":       "Директор\nБерлизева Алина Евгеньевна",
        "brand":        "Good Support",
        "seal":         os.path.join(HERE, "seal_smartforyou.png"),
        "seal_w":       38 * mm,
        "seal_ar":      379 / 391,
        "sig_img":      os.path.join(HERE, "signature_berlizeva.png"),
        "sig_img_w":    30 * mm,
        "sig_img_ar":   78 / 220,
    },
}


def detect_entity(entity_name: str) -> dict:
    name_lower = entity_name.lower()
    if "смарт" in name_lower or "smart" in name_lower:
        return ENTITIES["smart4yu"]
    return ENTITIES["ip"]


def parse_card_data(card_text: str) -> dict:
    """Parse extracted card text into structured fields.

    Expected input format (from Claude extraction):
        Компания: ООО «Ромашка»
        ИНН: 1234567890
        КПП: 123456789
        ОГРН: 1234567890123
        Адрес: 109028, г. Москва, ...
        Контакт: Иванов Иван Иванович
        Должность: Генеральный директор
        Телефон: +7 ...
        Email: ...
    """
    fields: dict = {}
    for line in card_text.split("\n"):
        if ":" in line:
            key, _, val = line.partition(":")
            fields[key.strip().lower()] = val.strip()

    # Normalise keys (Russian variants)
    def _get(*keys):
        for k in keys:
            v = fields.get(k)
            if v:
                return v
        return ""

    return {
        "company":  _get("компания", "организация", "company"),
        "inn":      _get("инн", "inn"),
        "address":  _get("адрес", "address"),
        "contact":  _get("контакт", "contact", "фио", "имя"),
        "position": _get("должность", "position", "роль"),
    }


def draw_header(c, entity: dict) -> float:
    """Draw letterhead header. Returns y position below divider."""
    y_top = PAGE_H - M_TOP

    # Logo
    logo_path = os.path.join(HERE, "logo_goodsupport.png")
    if os.path.exists(logo_path):
        logo_w = 55 * mm
        logo_h = logo_w * (188 / 674)
        c.drawImage(logo_path, M_LEFT, y_top - logo_h - 2 * mm,
                    width=logo_w, height=logo_h, mask="auto", preserveAspectRatio=True)

    # Company name + details (right side)
    x_right = PAGE_W - M_RIGHT
    line_y  = y_top - 4 * mm
    c.setFillColor(INK); c.setFont(FONT_BOLD, 11)
    c.drawRightString(x_right, line_y, entity["name"])

    line_y -= 5.5 * mm
    c.setFont(FONT_REGULAR, 9)
    ogrn_label = " · " + entity.get("ogrn_label", "ОГРН") + " "
    if entity.get("kpp"):
        parts = [
            ("ИНН ", INK), (entity["inn"], ORANGE),
            (" · КПП ", INK), (entity["kpp"], ORANGE),
            (ogrn_label, INK), (entity["ogrnip"], ORANGE),
        ]
    else:
        parts = [
            ("ИНН ", INK), (entity["inn"], ORANGE),
            (ogrn_label, INK), (entity["ogrnip"], ORANGE),
        ]
    full_w = sum(c.stringWidth(s, FONT_REGULAR, 9) for s, _ in parts)
    x_cur = x_right - full_w
    for s, color in parts:
        c.setFillColor(color); c.drawString(x_cur, line_y, s)
        x_cur += c.stringWidth(s, FONT_REGULAR, 9)

    line_y -= 5 * mm
    c.setFillColor(INK)
    c.drawRightString(x_right, line_y, entity["addr"])
    line_y -= 4.5 * mm
    c.drawRightString(x_right, line_y, entity["contact"])

    # Orange divider
    divider_y = y_top - 30 * mm
    c.setStrokeColor(ORANGE); c.setLineWidth(1.2)
    c.line(M_LEFT, divider_y, PAGE_W - M_RIGHT, divider_y)

    return divider_y


def draw_footer(c, entity: dict = None):
    """Draw page footer."""
    y = M_BOTTOM
    c.setStrokeColor(GREY); c.setLineWidth(0.5)
    c.line(M_LEFT, y + 5 * mm, PAGE_W - M_RIGHT, y + 5 * mm)
    c.setFillColor(MUTED); c.setFont(FONT_REGULAR, 8)
    footer_left = (entity or {}).get("footer_left", "Good Support · Официальное письмо")
    c.drawString(M_LEFT, y, footer_left)
    c.drawRightString(PAGE_W - M_RIGHT, y, datetime.now().strftime("%d.%m.%Y"))


def draw_recipient_block(c, card_text: str, y_start: float) -> float:
    """Draw right-aligned recipient block (like in reference template).

    Layout (right-aligned):
        Должность получателя         ← regular, INK
        Компания получателя          ← bold, INK
        Фамилия И. О.                ← bold, INK
        Адрес, г. Москва, ...        ← small, MUTED

    Returns y position below the block (with gap).
    """
    if not card_text or not card_text.strip():
        return y_start

    parsed = parse_card_data(card_text)
    x_right = PAGE_W - M_RIGHT
    y = y_start

    # Position / role
    if parsed.get("position"):
        c.setFont(FONT_REGULAR, 10); c.setFillColor(INK)
        c.drawRightString(x_right, y, parsed["position"])
        y -= 5.5 * mm

    # Company name (bold)
    if parsed.get("company"):
        c.setFont(FONT_BOLD, 10); c.setFillColor(INK)
        c.drawRightString(x_right, y, parsed["company"])
        y -= 5.5 * mm

    # Contact name (bold)
    if parsed.get("contact"):
        c.setFont(FONT_BOLD, 10); c.setFillColor(INK)
        c.drawRightString(x_right, y, parsed["contact"])
        y -= 5.5 * mm

    # Address (small, muted) — truncate if too long
    if parsed.get("address"):
        addr = parsed["address"]
        c.setFont(FONT_REGULAR, 8.5); c.setFillColor(MUTED)
        max_w = PAGE_W / 2  # right half only
        while addr and c.stringWidth(addr, FONT_REGULAR, 8.5) > max_w:
            addr = addr[:addr.rfind(",") if "," in addr else -3]
        c.drawRightString(x_right, y, addr)
        y -= 5 * mm

    return y - 8 * mm   # gap before date / body


def draw_body(c, text: str, entity: dict, date: str, start_y: float,
              recipient: str = "") -> float:
    """Render letter body (with optional recipient block). Returns final y."""
    text_w = PAGE_W - M_LEFT - M_RIGHT
    line_h = 5.5 * mm
    bottom_limit = M_BOTTOM + 55 * mm  # leave room for signature + seal

    y = start_y - 8 * mm

    # ── Recipient block (right-aligned, à la reference template) ──
    if recipient and recipient.strip():
        y = draw_recipient_block(c, recipient, y)

    # ── Date (right-aligned) ──
    if date:
        c.setFillColor(MUTED); c.setFont(FONT_REGULAR, 10)
        c.drawRightString(PAGE_W - M_RIGHT, y, date)
        y -= 10 * mm

    # ── Letter text ──
    c.setFillColor(INK); c.setFont(FONT_REGULAR, 10)

    for raw_line in text.split("\n"):
        # Empty line → paragraph gap
        if not raw_line.strip():
            y -= line_h * 0.6
            continue

        words = raw_line.split(" ")
        current = ""
        for word in words:
            test = (current + " " + word).strip()
            if c.stringWidth(test, FONT_REGULAR, 10) <= text_w:
                current = test
            else:
                if y < bottom_limit:
                    c.showPage()
                    draw_header(c, entity)
                    draw_footer(c, entity)
                    y = PAGE_H - M_TOP - 38 * mm
                    c.setFillColor(INK); c.setFont(FONT_REGULAR, 10)
                c.drawString(M_LEFT, y, current)
                y -= line_h
                current = word
        # Last chunk of line
        if y < bottom_limit:
            c.showPage()
            draw_header(c, entity)
            draw_footer(c, entity)
            y = PAGE_H - M_TOP - 38 * mm
            c.setFillColor(INK); c.setFont(FONT_REGULAR, 10)
        if current:
            c.drawString(M_LEFT, y, current)
            y -= line_h

    return y


def draw_signature(c, entity: dict, sig_y: float):
    """Draw signature block with real seal."""
    c.setFillColor(INK); c.setFont(FONT_REGULAR, 10)

    # Signer lines
    for i, line in enumerate(entity["signer"].split("\n")):
        c.drawString(M_LEFT, sig_y - i * 5.5 * mm, line)

    # Brand subtitle
    if entity.get("brand"):
        c.setFont(FONT_ITALIC, 9); c.setFillColor(MUTED)
        c.drawString(M_LEFT, sig_y - 11 * mm, entity["brand"])

    # Handwritten signature image (separate file, e.g. Smart4Yu)
    sig_img_path = entity.get("sig_img", "")
    if sig_img_path and os.path.exists(sig_img_path):
        sig_img_w = entity.get("sig_img_w", 30 * mm)
        sig_img_h = sig_img_w * entity.get("sig_img_ar", 78 / 220)
        c.drawImage(sig_img_path, M_LEFT + 50 * mm, sig_y - 14 * mm,
                    width=sig_img_w, height=sig_img_h, mask="auto", preserveAspectRatio=True)

    # Signature line
    c.setStrokeColor(INK); c.setLineWidth(0.6); c.setDash()
    line_y = sig_y - 23 * mm
    c.line(M_LEFT, line_y, M_LEFT + 80 * mm, line_y)
    c.setFillColor(MUTED); c.setFont(FONT_ITALIC, 8)
    name_short = entity["signer"].split("\n")[-1].split()
    initials = name_short[0] + " " + " ".join(p[0] + "." for p in name_short[1:]) if len(name_short) > 1 else name_short[0]
    c.drawString(M_LEFT, line_y - 4 * mm, f"подпись / {initials} /")

    # Seal PNG
    seal_path = entity.get("seal", "")
    if seal_path and os.path.exists(seal_path):
        seal_w = entity.get("seal_w", 65 * mm)
        seal_h = seal_w * entity.get("seal_ar", 1.0)
        seal_x = PAGE_W - M_RIGHT - seal_w
        c.drawImage(seal_path, seal_x, line_y - 2 * mm,
                    width=seal_w, height=seal_h, mask="auto", preserveAspectRatio=True)


def draw_letter(buffer: io.BytesIO, text: str, entity_name: str,
                date: str, recipient: str = "") -> None:
    entity = detect_entity(entity_name)
    c = canvas.Canvas(buffer, pagesize=A4)
    divider_y = draw_header(c, entity)
    draw_footer(c, entity)
    final_y = draw_body(c, text, entity, date, divider_y, recipient=recipient)
    sig_y = M_BOTTOM + 48 * mm
    draw_signature(c, entity, sig_y)
    c.showPage()
    c.save()


# ── Models ──
class LetterRequest(BaseModel):
    text: str
    entity_name: str = "ИП Лапшенков"
    date: str = ""
    seal: bool = True
    recipient: str = ""   # raw card_data text from Claude extraction


class SendLetterRequest(BaseModel):
    text: str
    entity_name: str = "ИП Лапшенков"
    date: str = ""
    seal: bool = True
    chat_id: str
    bot_token: str
    caption: str = ""
    recipient: str = ""   # raw card_data text from Claude extraction


# ── Endpoints ──
@app.post("/generate")
async def generate_pdf(req: LetterRequest):
    buf = io.BytesIO()
    draw_letter(buf, req.text, req.entity_name, req.date, req.recipient)
    return JSONResponse({"pdf_base64": base64.b64encode(buf.getvalue()).decode()})


@app.post("/send")
async def send_letter(req: SendLetterRequest):
    """Generate PDF with real letterhead and send directly to Telegram."""
    buf = io.BytesIO()
    draw_letter(buf, req.text, req.entity_name, req.date, req.recipient)
    pdf_bytes = buf.getvalue()

    fname   = f"Письмо_{datetime.now().strftime('%Y-%m-%d')}.pdf"
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
    return JSONResponse(
        {"success": False, "error": result.get("description", "Telegram error")},
        status_code=500
    )


@app.get("/health")
async def health():
    assets = {
        "logo":          os.path.exists(os.path.join(HERE, "logo_goodsupport.png")),
        "seal_ip":       os.path.exists(os.path.join(HERE, "seal_lapshenkov.png")),
        "seal_smart4yu": os.path.exists(os.path.join(HERE, "seal_smartforyou.png")),
    }
    return {"status": "ok", "font": FONT_REGULAR, "assets": assets}
