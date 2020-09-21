# Streaming mic audio from browser to server through web socket
- Works with Chrome, Firefox. Doesn't work with Safari though.
- Recording 8khz 16 bit signed int PCM WAV mono audio is shown, but you can adjust that with the help of `RecordRTC.js` https://recordrtc.org/.

To run server (requires python3.6+):
```
pip install -r requirements.txt
python src/server.py
```

Then visit `localhost:8000` in your browser to test the demo.

Everything required on client side can be found in `index.html` and `index.js` + `RecordRTC.js` https://recordrtc.org/.


Instead of server written on python, you could use any other server of your liking, which supports web sockets, or choose another protocol to send audio from browser to server.

**Note:**
If hosting on server, https is required to be able to record audio in browser, though for debug purposes, self hosting works fine.
