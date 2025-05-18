from flask import Flask, send_from_directory
from flask_cors import CORS  # 新增导入
app = Flask(__name__)
CORS(app)

@app.route('/')
def index():
    return send_from_directory('.', 'video_player.html')

@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory('js', filename)

@app.route('/lang-data/tessdata-main/<path:filename>')
def tessdata_js(filename):
    return send_from_directory('lang-data/tessdata-main', filename)

if __name__ == '__main__':
    app.run('0.0.0.0', 9009)
