var socket;



function onAudioStreamReceived(stream) {
    document.getElementById("start").disabled = true;
    document.getElementById("stop").disabled = false;

    var ws_url = "ws://localhost:8000/ws";
    console.log("web socket url", ws_url);

    socket = new WebSocket(ws_url);

    socket.onopen = function() {
        console.log("Web socket connection established.");
    };

    socket.onclose = function(event) {
        if (event.wasClean) {
            console.log('Web socket connection closed');
        } else {
            console.log('Web socket connection fault');
        }
        console.log('Code: ' + event.code + ' reason: ' + event.reason);
    };

    socket.onerror = function(error) {
        console.log("Error " + error.message);
    };

    socket.onmessage = function(event) {
        var recordAudio;
        var startTime;
        var totalSent;

        var curId = event.data;
        console.log("Received audio id", curId);

        socket.onmessage = function(event) {
            console.log("Recevied from server", event.data);
        };

        recordAudio = RecordRTC(stream, {
            type: 'audio',
            mimeType: 'audio/wav',  // recording in wav
            sampleRate: 44000,
            desiredSampRate: 8000,  // output will be in 8khz

            recorderType: StereoAudioRecorder,  // required by lib
            numberOfAudioChannels: 1,  // recording mono

            timeSlice: 500,  // new audio chunk will be awailable in 500 ms

            ondataavailable: function(blob) {

                var fileReader = new FileReader();
                fileReader.readAsArrayBuffer(blob);
                fileReader.onload = function(event) {
                    var arrayBuffer = fileReader.result;
                    var arr = new Uint8Array(arrayBuffer);
                    console.log("Sending", arr.length);
                    socket.send(arr);
                    totalSent += arr.length
                };
            }
        });

        totalSent = 0;
        recordAudio.startRecording();

        document.getElementById("status").innerText = "Recording...";
        startTime = new Date();

        var updateTimer = setInterval(function () {
            document.getElementById("time").innerText = Math.floor((new Date() - startTime) / 1000) + "";
        }, 1000)

        document.getElementById("stop").onclick = function () {
            document.getElementById("start").disabled = false;
            document.getElementById("stop").disabled = true;

            recordAudio.stopRecording();
            document.getElementById("status").innerText = "Waiting...";
            clearInterval(updateTimer);
            socket.close();

            // window.setTimeout(function () {
            //     socket.close()
            //     $.ajax({
            //         url: '/stop?id=' + curId,
            //         method: 'get'
            //     }).done(function(resp) {
            //         console.log("Stop response:", resp);
            //     });
            //
            // }, 20000);

        };
    };
}

function onStartRecording () {
    navigator.getUserMedia(
        {
            audio: true
        },
        onAudioStreamReceived,
        function(error) {
            console.error("Error connecting to audio api", error, JSON.stringify(error));
        }
    );
}

window.onload = function() {
    document.getElementById("start").disabled = false;
    document.getElementById("stop").disabled = true;
    document.getElementById("start").onclick = onStartRecording;
};
