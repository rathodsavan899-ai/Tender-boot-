"""Content assistant: one truthful Marathi poster + caption + 30-second video script per day.

Truth rules: topics are limited to features that really exist; a topic that depends on data or a key we do not have
yet (awarded-tender data, OpenAI) is skipped; the "tender of the day" poster only shows tenders actually found today
on public portals. No testimonials, no guarantees. Each post is sent to the owner (Telegram) and, if the Meta
settings are present, published to the Facebook Page and Instagram account (max one post per day).
"""
from __future__ import annotations

import io
import json
import secrets
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agents import communication_agent, logger, poster_pro, video_agent
from config import get_settings
from database import AwardedTender, ContentPost, ContentVideo, PosterBackground, SessionLocal, Tender, utcnow

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
IST = timezone(timedelta(hours=5, minutes=30))
HASHTAGS = "#टेंडर #कंत्राटदार #महाराष्ट्र #सिव्हिल #PWD #TenderBotAI"
MIN_AWARDED_FOR_BID_POST = 20

TOPICS = [
    {"key": "search", "screen": "टेंडर शोध", "requires": None,
     "headline": "नवीन टेंडर शोधा, एकाच जागी",
     "points": ["सार्वजनिक पोर्टल्सवरील नवे टेंडर आपोआप गोळा", "कीवर्ड, जिल्हा आणि किंमतीनुसार शोध", "शेवटची तारीख एका नजरेत"]},
    {"key": "eligibility", "screen": "पात्रता तपासणी", "requires": None,
     "headline": "टेंडर भरण्याआधी कळेल, कोणते कागदपत्र कमी आहे",
     "points": ["निविदेतील कागदपत्रांशी तुमची कागदपत्रे जुळवा", "वर्ग आणि उलाढालीची अट तपासा", "चुकीचे टेंडर भरण्याचा धोका टळतो"]},
    {"key": "approval", "screen": "सबमिशन मंजुरी", "requires": None,
     "headline": "तुमच्या OK शिवाय काहीही सबमिट होत नाही",
     "points": ["बिड रक्कम तुम्ही पाहून मंजूर करता", "ॲपमध्येच होय / नाही", "स्टेटस स्पष्ट दिसतो"]},
    {"key": "vault", "screen": "कागदपत्र व्हॉल्ट", "requires": None,
     "headline": "सर्व कागदपत्रे एका सुरक्षित जागी",
     "points": ["आधार, GST, PAN, PWD नोंदणी अपलोड", "फाइल एन्क्रिप्ट करून साठवली जाते", "मुदत संपणारी कागदपत्रे होमवर दिसतात"]},
    {"key": "gst", "screen": "GST सल्ला", "requires": None,
     "headline": "GST आणि ITC चा हिशोब सोपा",
     "points": ["करपात्र मूल्यावर GST देय पाहा", "पात्र ITC वजा करून निव्वळ देय", "सीए ला शेअर करता येईल असा तपशील"]},
    {"key": "chat", "screen": "AI सहाय्यक", "requires": "openai",
     "headline": "मराठीत विचारा, AI उत्तर देईल",
     "points": ["टेंडरला कोणती कागदपत्रे लागतात?", "GST, ITC आणि अटींचे प्रश्न", "तुमच्या कागदपत्रांनुसार उत्तर"]},
    {"key": "bid", "screen": "बिड रेट", "requires": "awarded_data",
     "headline": "जुन्या निकालांवरून अंदाजे L1 रेट",
     "points": ["सार्वजनिक अवार्ड डेटावर आधारित", "तुमचा खर्च टाकून नफा पाहा", "डेटा कमी असेल तर तसे स्पष्ट सांगतो"]},
    {"key": "trial", "screen": "होम", "requires": None,
     "headline": "१५ दिवस मोफत वापरून पाहा",
     "points": ["टेंडर शोध, पात्रता, GST हिशोब", "कागदपत्र व्हॉल्ट आणि AI सहाय्यक", "सुरू करण्यासाठी फक्त मोबाइल नंबर"]},
]


class PosterUnavailable(RuntimeError):
    pass


def ist_today() -> date:
    return datetime.now(IST).date()


# ------------------------------------------------------------------ poster
def _wrap(draw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        while draw.textlength(word, font=font) > max_width and len(word) > 1:   # very long word: break it
            cut = len(word) - 1
            while cut > 1 and draw.textlength(word[:cut], font=font) > max_width:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        current = word
    if current:
        lines.append(current)
    return lines


def render_poster(headline: str, points: list[str], note: str | None = None, link: str = "", compact: bool = False) -> bytes:
    """1080x1350 PNG (Instagram 4:5). Raises PosterUnavailable if Marathi shaping (raqm) or the fonts are missing."""
    from PIL import Image, ImageDraw, ImageFont, features

    bold_path, regular_path = FONT_DIR / "Poppins-Bold.ttf", FONT_DIR / "Poppins-Regular.ttf"
    if not (bold_path.exists() and regular_path.exists()):
        raise PosterUnavailable("fonts missing")
    if not features.check("raqm"):
        raise PosterUnavailable("raqm text layout not available (Marathi would render incorrectly)")

    width, height = 1080, 1350
    top, bottom = (11, 42, 74), (21, 96, 168)
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / (height - 1)
        draw.line([(0, y), (width, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))

    orange, white = (255, 159, 28), (255, 255, 255)
    brand = ImageFont.truetype(str(bold_path), 46)
    draw.text((70, 70), "TenderBot AI", font=brand, fill=white)
    draw.rounded_rectangle((70, 138, 250, 146), radius=4, fill=orange)

    margin, text_width = 70, width - 140
    size = 96
    while True:                                         # shrink the headline until it fits in 4 lines
        head_font = ImageFont.truetype(str(bold_path), size)
        head_lines = _wrap(draw, headline, head_font, text_width)
        if len(head_lines) <= 4 or size <= 56:
            break
        size -= 6
    y = 210
    line_h = int(size * 1.45)
    for line in head_lines[:4]:
        draw.text((margin, y), line, font=head_font, fill=white)
        y += line_h

    y += 40
    body = ImageFont.truetype(str(regular_path), 40 if compact else 48)
    step, gap = (58, 22) if compact else (72, 26)
    footer_top = height - 330
    for point in points:
        lines = _wrap(draw, point, body, text_width - 70)
        if compact and len(lines) > 2:                      # long tender titles: keep two lines
            lines = lines[:2]
            lines[1] = lines[1].rstrip(" …") + "…"
        block = len(lines) * step + gap
        if y + block > footer_top - (60 if note else 0):
            break
        draw.ellipse((margin, y + 22, margin + 30, y + 52), fill=orange)
        draw.line([(margin + 8, y + 37), (margin + 13, y + 44), (margin + 23, y + 30)], fill=(11, 42, 74), width=5)
        for line in lines:
            draw.text((margin + 62, y), line, font=body, fill=white)
            y += step
        y += gap

    if note:
        small = ImageFont.truetype(str(regular_path), 30)
        for i, line in enumerate(_wrap(draw, note, small, text_width)[:2]):
            draw.text((margin, footer_top - 62 + i * 40), line, font=small, fill=(190, 210, 235))

    draw.rounded_rectangle((margin, footer_top + 10, width - margin, footer_top + 150), radius=36, fill=orange)
    cta = ImageFont.truetype(str(bold_path), 58)
    cta_text = "१५ दिवस मोफत ट्रायल"
    draw.text(((width - draw.textlength(cta_text, font=cta)) / 2, footer_top + 38), cta_text, font=cta, fill=(11, 42, 74))
    if link:
        small = ImageFont.truetype(str(regular_path), 36)
        draw.text(((width - draw.textlength(link, font=small)) / 2, footer_top + 195), link, font=small, fill=white)
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()


# ------------------------------------------------------------------ content
def _topic_allowed(db: Session, topic: dict) -> bool:
    need = topic["requires"]
    if need == "openai":
        return bool(get_settings().openai_api_key)
    if need == "awarded_data":
        return (db.scalar(select(func.count(AwardedTender.id))) or 0) >= MIN_AWARDED_FOR_BID_POST
    return True


def _tender_topic(db: Session) -> dict | None:
    """'Tender of the day' built only from tenders really found in the last 24 hours."""
    since = utcnow() - timedelta(hours=24)
    rows = list(db.scalars(select(Tender).where(
        Tender.created_at >= since, (Tender.closing_date.is_(None)) | (Tender.closing_date >= ist_today()))
        .order_by(Tender.created_at.desc())))
    if not rows:
        return None
    points, shown = [], []
    for t in rows[:3]:
        title = t.title if len(t.title) <= 64 else t.title[:61] + "…"
        date_text = t.closing_date.strftime("%d/%m") if t.closing_date else None
        points.append((f"{date_text} पर्यंत — " if date_text else "") + title)
        shown.append({"title": title, "date": date_text})
    return {"key": "tender_of_day", "kind": "tender", "screen": "टेंडर शोध", "points": points, "rows": shown,
            "card_points": ["सार्वजनिक पोर्टलवरून गोळा केलेले", "शेवटची तारीख एका नजरेत", "ॲपमध्ये पात्रता तपासा"],
            "headline": f"आज {len(rows)} नवे टेंडर सापडले", "note": "स्रोत: CPPP सार्वजनिक यादी. अधिकृत माहिती पोर्टलवर तपासा."}


def pick_topic(db: Session, today: date) -> dict:
    if today.toordinal() % 2 == 0:
        tender_topic = _tender_topic(db)
        if tender_topic:
            return tender_topic
    allowed = [t for t in TOPICS if _topic_allowed(db, t)]
    return {**allowed[(today.toordinal() // 2) % len(allowed)], "kind": "feature", "note": None}


def _ai_background(db: Session) -> bytes | None:
    """Rotate through stored AI pictures; make at most one new picture per day (up to 6) when enabled."""
    s = get_settings()
    stored = list(db.scalars(select(PosterBackground).order_by(PosterBackground.id)))
    if s.content_ai_background and s.openai_api_key and len(stored) < 6 and not any(
            b.created_at.date() == utcnow().date() for b in stored):
        try:
            r = httpx.post("https://api.openai.com/v1/images/generations", timeout=180,
                           headers={"Authorization": f"Bearer {s.openai_api_key}"},
                           json={"model": s.openai_image_model, "prompt": poster_pro.BACKGROUND_PROMPT,
                                 "size": "1024x1536", "quality": "medium", "n": 1})
            item = r.json()["data"][0]
            import base64
            png = base64.b64decode(item["b64_json"]) if item.get("b64_json") else httpx.get(item["url"], timeout=60).content
            row = PosterBackground(png=png)
            db.add(row)
            db.commit()
            stored.append(row)
        except Exception as exc:                      # never leak the key: only the exception type is logged
            logger.warning("AI background not created: %s", type(exc).__name__)
    return stored[ist_today().toordinal() % len(stored)].png if stored else None


def build_caption(topic: dict, link: str) -> str:
    bullets = "\n".join(f"✅ {p}" for p in topic["points"])
    note = f"\n\n{topic['note']}" if topic.get("note") else ""
    return f"{topic['headline']}\n\n{bullets}{note}\n\n📲 TenderBot AI — १५ दिवस मोफत ट्रायल\n{link}\n\n{HASHTAGS}"


def build_script(topic: dict, link_text: str) -> str:
    body = " ".join(topic["points"])
    return (f"🎬 ३० सेकंदांचा व्हिडिओ (स्क्रीन: {topic['screen']})\n"
            f"०-५ से (हुक): {topic['headline']}\n"
            f"५-२० से (स्क्रीन रेकॉर्डिंगवर बोला): {body}\n"
            f"२०-३० से (शेवट): TenderBot AI. १५ दिवस मोफत ट्रायल. लिंक वर्णनात: {link_text}")


# ------------------------------------------------------------------ publishing
def _meta(path: str) -> str:
    s = get_settings()
    return f"https://graph.facebook.com/{s.meta_graph_version}/{path}"


def _meta_error(response: httpx.Response) -> str:
    try:
        return str(response.json().get("error", {}).get("message", ""))[:160]
    except Exception:
        return f"http {response.status_code}"


def _public(post: ContentPost, kind: str, ext: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/content/{kind}/{post.public_token}.{ext}"


def post_facebook(post: ContentPost, has_video: bool = False) -> dict | None:
    s = get_settings()
    if not (s.facebook_page_id and s.facebook_page_token):
        return None
    video_error = None
    try:
        if has_video:
            r = httpx.post(_meta(f"{s.facebook_page_id}/videos"), timeout=120,
                           data={"file_url": _public(post, "video", "mp4"), "description": post.caption,
                                 "access_token": s.facebook_page_token})
            if r.status_code == 200 and "id" in r.json():
                return {"ok": True, "type": "video"}
            video_error = _meta_error(r)
        if post.poster_png:
            r = httpx.post(_meta(f"{s.facebook_page_id}/photos"), timeout=60,
                           data={"caption": post.caption, "access_token": s.facebook_page_token},
                           files={"source": ("poster.png", post.poster_png, "image/png")})
        else:
            r = httpx.post(_meta(f"{s.facebook_page_id}/feed"), timeout=60,
                           data={"message": post.caption, "access_token": s.facebook_page_token})
        ok = r.status_code == 200 and "id" in r.json()
        out = {"ok": ok, "type": "photo"}
        if not ok:
            out["error"] = _meta_error(r)
        if video_error:
            out["video_error"] = video_error
        return out
    except Exception as exc:
        logger.error("facebook post failed: %s", type(exc).__name__)
        return {"ok": False, "error": type(exc).__name__}


def _ig_publish(container: str) -> dict:
    s = get_settings()
    published = httpx.post(_meta(f"{s.instagram_business_id}/media_publish"), timeout=60,
                           data={"creation_id": container, "access_token": s.facebook_page_token})
    ok = published.status_code == 200 and "id" in published.json()
    return {"ok": ok, **({} if ok else {"error": _meta_error(published)})}


def post_instagram(post: ContentPost, has_video: bool = False) -> dict | None:
    s = get_settings()
    if not (s.instagram_business_id and s.facebook_page_token):
        return None
    base = _meta(f"{s.instagram_business_id}/media")
    video_error = None
    try:
        if has_video:                                   # Reel: create the container, wait until Instagram has processed it
            created = httpx.post(base, timeout=60, data={
                "media_type": "REELS", "video_url": _public(post, "video", "mp4"), "share_to_feed": "true",
                "caption": post.caption[:2200], "access_token": s.facebook_page_token})
            container = created.json().get("id")
            if created.status_code == 200 and container:
                for _ in range(18):
                    time.sleep(10)
                    status = httpx.get(_meta(container), timeout=30,
                                       params={"fields": "status_code", "access_token": s.facebook_page_token}).json().get("status_code")
                    if status == "FINISHED":
                        return {**_ig_publish(container), "type": "reel"}
                    if status in ("ERROR", "EXPIRED"):
                        video_error = f"processing {status}"
                        break
                else:
                    video_error = "processing timed out"
            else:
                video_error = _meta_error(created)
        if not post.poster_png:
            return {"ok": False, "error": video_error or "no image"}
        created = httpx.post(base, timeout=60, data={"image_url": _public(post, "poster", "png"),
                                                     "caption": post.caption[:2200], "access_token": s.facebook_page_token})
        container = created.json().get("id")
        if created.status_code != 200 or not container:
            return {"ok": False, "error": _meta_error(created), **({"video_error": video_error} if video_error else {})}
        time.sleep(6)
        out = {**_ig_publish(container), "type": "photo"}
        if video_error:
            out["video_error"] = video_error
        return out
    except Exception as exc:
        logger.error("instagram post failed: %s", type(exc).__name__)
        return {"ok": False, "error": type(exc).__name__}


def deliver(db: Session, post: ContentPost) -> dict:
    """Owner copy (Telegram) first, then the social accounts that are configured."""
    result: dict = {}
    video = db.scalar(select(ContentVideo).where(ContentVideo.post_id == post.id))
    summary = f"📣 आजचा मजकूर तयार\n\n{post.caption}\n\n{post.script}"
    if post.poster_png:
        result["telegram_photo"] = communication_agent.notify_admin_photo(post.poster_png, post.headline[:200])
    if video:
        result["telegram_video"] = communication_agent.notify_admin_video(video.mp4, post.headline[:200])
    result["telegram_text"] = communication_agent.notify_admin(summary)
    facebook, instagram = post_facebook(post, bool(video)), post_instagram(post, bool(video))
    if facebook is not None:
        result["facebook"] = facebook
    if instagram is not None:
        result["instagram"] = instagram
    post.delivery = json.dumps(result, ensure_ascii=False, default=str)
    post.status = "posted" if any(isinstance(v, dict) and v.get("ok") for k, v in result.items() if k in ("facebook", "instagram")) else "sent"
    db.commit()
    return result


def generate_today(db: Session, force: bool = False) -> ContentPost:
    today = ist_today()
    existing = db.scalar(select(ContentPost).where(ContentPost.post_date == today).order_by(ContentPost.id.desc()))
    if existing is not None and not force:
        return existing
    s = get_settings()
    link = s.public_base_url.rstrip("/") + "/app"
    topic = pick_topic(db, today)
    poster, poster_error = None, None
    short_link = link.replace("https://", "").replace("http://", "")
    background = _ai_background(db)
    try:
        try:
            poster = poster_pro.render_poster_pro(topic["headline"], topic.get("card_points") or topic["points"],
                                                  topic.get("note"), short_link, topic.get("rows"), background)
        except poster_pro.PosterUnavailable:
            raise
        except Exception as exc:                      # pro layout failed: fall back to the simple poster
            logger.warning("pro poster failed (%s); using the simple layout", type(exc).__name__)
            poster = render_poster(topic["headline"], topic["points"], topic.get("note"), short_link,
                                   compact=topic["kind"] == "tender")
    except (PosterUnavailable, poster_pro.PosterUnavailable) as exc:
        poster_error = str(exc)
        logger.warning("poster not generated: %s", poster_error)
    post = ContentPost(post_date=today, kind=topic["kind"], topic_key=topic["key"], headline=topic["headline"],
                       caption=build_caption(topic, link), script=build_script(topic, link), poster_png=poster,
                       public_token=secrets.token_urlsafe(18), status="draft",
                       delivery=json.dumps({"poster_error": poster_error}) if poster_error else "")
    db.add(post)
    db.commit()
    db.refresh(post)
    if s.content_video and poster_error is None:
        made = video_agent.make_video(topic["headline"], topic["points"], topic.get("rows"), short_link, background)
        if made:
            db.add(ContentVideo(post_id=post.id, mp4=made[0], seconds=made[1]))
            db.commit()
    deliver(db, post)
    for old in db.scalars(select(ContentPost).where(ContentPost.post_date < today - timedelta(days=45))):
        db.delete(old)
    db.commit()
    return post


def run_daily_job(force: bool = False) -> dict:
    """Scheduler entry: runs once per IST day, after CONTENT_HOUR_IST."""
    if not force and datetime.now(IST).hour < get_settings().content_hour_ist:
        return {"skipped": "too early"}
    with SessionLocal() as db:
        post = generate_today(db, force=force)
        return {"post_id": post.id, "status": post.status, "topic": post.topic_key}
