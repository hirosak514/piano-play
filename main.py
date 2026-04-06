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

# CORS設定（GitHub Pagesからのアクセスを許可）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Renderの環境変数からAPIキーを取得
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# music21の設定（サーバー環境でのエラーを回避）
from music21 import environment
try:
    environment.UserSettings()['graphicsMagickPath'] = ''
    environment.UserSettings()['musescoreDirectPNGPath'] = ''
except:
    pass

@app.post("/generate-midi")
async def generate_midi(file: UploadFile = File(...)):
    # 2. 画像の読み込み
    try:
        contents = await file.read()
        base64_image = base64.b64encode(contents).decode('utf-8')
    except Exception:
        raise HTTPException(status_code=400, detail="画像の読み込みに失敗しました")

    # 3. OpenAI API (GPT-4o) で解析
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
                            "text": "この楽譜の音符を解析して、以下のJSON形式で出力してください。durationは4分音符を1.0とした長さです。\n\n{\"notes\": [{\"pitch\": \"C4\", \"duration\": 1.0}]}"
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
        
        analysis_result = json.loads(response.choices[0].message.content)
        notes_data = analysis_result.get("notes", [])

    except Exception as e:
        print(f"API Error: {e}")
        raise HTTPException(status_code=500, detail="AIの解析中にエラーが発生しました")

    # 4. music21でMIDIデータを構築
    try:
        s = music21.stream.Stream()
        for item in notes_data:
            # 念のためデータが存在することを確認
            if 'pitch' in item and 'duration' in item:
                n = music21.note.Note(item['pitch'])
                n.quarterLength = float(item['duration'])
                s.append(n)

        # 【超重要修正】一時ファイルを使用してバイナリを取得
        # これにより、ライブラリのバージョンに関わらず「write()」のエラーを回避できます
        temp_midi_path = "/tmp/output.mid"
        s.write('midi', fp=temp_midi_path)
        
        with open(temp_midi_path, "rb") as f:
            midi_data = f.read()
        
        # 使用後の一時ファイルを削除（任意）
        if os.path.exists(temp_midi_path):
            os.remove(temp_midi_path)

        # 5. フロントエンドに送信
        return StreamingResponse(
            io.BytesIO(midi_data),
            media_type="audio/midi",
            headers={"Content-Disposition": "attachment; filename=output.mid"}
        )

    except Exception as e:
        print(f"MIDI Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"MIDI生成エラー: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
