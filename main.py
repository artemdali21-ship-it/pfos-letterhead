from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import base64, html as html_lib
from weasyprint import HTML

app = FastAPI()

class LetterRequest(BaseModel):
    text: str
    entity_name: str = "ИП Лапшенков"
    date: str = ""
    seal: bool = True

# CSS braces escaped as {{ }} for Python .format()
HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: 'DejaVu Serif', 'Times New Roman', Georgia, serif;
  font-size: 12pt;
  color: #1a1a1a;
  padding: 2.5cm 3cm 3cm 3cm;
}}
.header {{
  text-align: center;
  border-bottom: 2px solid #2c3e50;
  padding-bottom: 0.8cm;
  margin-bottom: 1.2cm;
}}
.company-name {{
  font-size: 16pt;
  font-weight: bold;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #2c3e50;
}}
.company-tagline {{
  font-size: 9pt;
  color: #7f8c8d;
  margin-top: 0.2cm;
}}
.date {{
  text-align: right;
  margin-bottom: 0.8cm;
  font-size: 11pt;
  color: #555;
}}
.letter-body {{
  line-height: 1.8;
  white-space: pre-wrap;
  word-wrap: break-word;
  font-size: 12pt;
}}
.footer {{
  margin-top: 2.5cm;
  border-top: 1px solid #bdc3c7;
  padding-top: 0.6cm;
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
}}
.seal-area {{
  width: 4cm;
  height: 4cm;
  border: 3px solid #2c3e50;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  font-size: 7pt;
  color: #2c3e50;
  font-weight: bold;
  padding: 0.3cm;
  line-height: 1.4;
}}
</style>
</head>
<body>
<div class="header">
  <div class="company-name">{entity_name}</div>
  <div class="company-tagline">GoodSupport &middot; Официальное письмо</div>
</div>
<div class="date">{date}</div>
<div class="letter-body">{text_escaped}</div>
<div class="footer">
  <div></div>
  <div class="seal-area">М.П.<br><br>ПЕЧАТЬ<br>{entity_short}</div>
</div>
</body>
</html>"""


@app.post("/generate")
async def generate_pdf(req: LetterRequest):
    text_escaped = html_lib.escape(req.text)
    entity_short = req.entity_name.replace("ООО ", "").replace("ИП ", "")[:12]

    html_content = HTML_TEMPLATE.format(
        entity_name=html_lib.escape(req.entity_name),
        date=html_lib.escape(req.date) if req.date else "",
        text_escaped=text_escaped,
        entity_short=html_lib.escape(entity_short),
    )

    pdf_bytes = HTML(string=html_content).write_pdf()
    return JSONResponse({"pdf_base64": base64.b64encode(pdf_bytes).decode()})


@app.get("/health")
async def health():
    return {"status": "ok"}
