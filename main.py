import os
import io
import json
import base64
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
import music21

# 1. 初期設定
app = FastAPI()

# CORS設定（GitHub Pagesなどの外部フロントエンドからのアクセスを許可）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 開発時は"*"でOK。本番ではGitHub PagesのURLを指定すると安全
    allow_methods=["*"],
    allow_headers=["*"],
)

# Renderの環境変数からAPIキーを取得
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# music21の設定（サーバー環境ではGUIを使わない設定にする）
music21.environment.set('graphicsMagickPath', '')
music21.environment.set('musescoreDirectPNGPath', '')

@app.post("/generate-midi")
async def generate_midi(file: UploadFile = File(...)):
    # 2. アップロードされた画像をbase64エンコード
    try:
        contents = await file.read()
        base64_image = base64.b64encode(contents).decode('utf-8')
    except Exception:
        raise HTTPException(status_code=400, detail="画像の読み込みに失敗しました")

    # 3. OpenAI API (GPT-4o) で画像を解析
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "あなたは楽譜を正確に解析する音楽家です。画像から音符を抽出し、指定されたJSON形式で回答してください。"
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text", 
                            "text": "この楽譜の音符を解析して、以下のJSON形式で出力してください。和音がある場合は複数の音符を含めてください。durationは4分音符を1.0とした長さです。\n\n{\"notes\": [{\"pitch\": \"C4\", \"duration\": 1.0}, {\"pitch\": \"E4\", \"duration\": 1.0}]}"
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{base64_image}"}
                        }
                    ],
                }
            ],
            response_format={ "type": "json_object" }
        )
        
        # 解析結果のJSONを取得
        analysis_result = json.loads(response.choices[0].message.content)
        notes_data = analysis_result.get("notes", [])

    except Exception as e:
        print(f"API Error: {e}")
        raise HTTPException(status_code=500, detail="AIの解析中にエラーが発生しました")

    # 4. music21でMIDIデータを構築
    try:
        s = music21.stream.Stream()
        for item in notes_data:
            # 音高(pitch)と長さ(duration)を指定して音符を作成
            n = music21.note.Note(item['pitch'])
            n.quarterLength = float(item['duration'])
            s.append(n)

        # MIDIをバイナリ（バイト列）に変換
        midi_fp = music21.midi.translate.streamToMidiFile(s)
        midi_data = midi_fp.write('midi')
        
        # 5. フロントエンドにMIDIファイルをストリーミング送信
        return StreamingResponse(
            io.BytesIO(midi_data),
            media_type="audio/midi",
            headers={"Content-Disposition": "attachment; filename=output.mid"}
        )

    except Exception as e:
        print(f"MIDI Error: {e}")
        raise HTTPException(status_code=500, detail="MIDI生成中にエラーが発生しました")

if __name__ == "__main__":
    import uvicorn
    # Renderなどのポート指定に対応
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
