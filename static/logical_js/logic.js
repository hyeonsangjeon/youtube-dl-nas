var wsEventBus = null;  //eventBus register flag

$(function () {

    //websocket support
    if (!window.WebSocket) {
        if (window.MozWebSocket) {
            window.WebSocket = window.MozWebSocket;
        } else {
            $('#messages').append("<li>Your browser doesn't support WebSockets.</li>");
        }
    }

    if(wsEventBus==null){
        wsEventBus = new WebSocket('ws://localhost:8080/websocket');
        console.log("Server EventBus websocket was created");

        wsEventBus.onopen = function(evt) {
            messagesTxt("WebSocket connection opened.");
        }

        wsEventBus.onmessage = function(evt) {
            messagesTxt( evt.data);
        }

        wsEventBus.onclose = function(evt) {
            messagesTxt("WebSocket connection closed.");
        }

    }

    $(document).on("click","#send",function(){

        var data={};
        data.url = $("#url").val();

        $.ajax({
            method : "POST"
            , url : "http://localhost:8080/youtube-dl/q"
            , data : JSON.stringify(data)
            , dataType : "json"
            , contentType: "application/json"
            , success:function(data,status){
                window.setTimeout(function(){
                    messagesTxt(data.msg);
                },400);
                //
            }
            , error:function (jqXHR, textStatus, errorThrown) {
                if(jqXHR.status==422){
                    custAlert("해당 서비스 이름은 사용할 수 없습니다. 다시 선택해주세요. ", "red");

                }else if(jqXHR.status==500){
                    custAlert(errorThrown +":내부 오류입니다. 잠시 후 다시 사용해주세요.","red");
                }else{
                    alert("내부 오류입니다. 잠시 후 다시 사용해주세요.");
                }
                console.log("jqXHR"+jqXHR);
                console.log("jqXHR"+jqXHR.status);
                console.log("textStatus"+textStatus);
                console.log("errorThrown"+errorThrown);
            }
        });

        $('#message').val('').focus();

        return false;
    });


    function messagesTxt(msg){
        $('#messages').html('<li>' + msg + '</li>');
    };

});
