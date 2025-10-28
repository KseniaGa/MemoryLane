using UnityEngine;
using UnityEngine.Networking;
using TMPro;
using System.Text;
using System.Threading.Tasks;

public class PondUnityDemo : MonoBehaviour
{
    [Header("UI References")]
    public TMP_InputField TitleField;
    public TMP_InputField OfferingField;
    public TMP_InputField ReplyField;
    public TextMeshProUGUI OutputText;

    private string baseUrl = "http://127.0.0.1:8000";
    private string sessionId;

    private void Awake()
    {
        sessionId = System.Guid.NewGuid().ToString();
        OutputText.text = "🌊 Ready to begin.";
    }

    // ---------- helpers ----------
    private async Task<string> PostJson(string endpoint, string json)
    {
        using var req = new UnityWebRequest($"{baseUrl}{endpoint}", "POST");
        byte[] body = Encoding.UTF8.GetBytes(json);
        req.uploadHandler = new UploadHandlerRaw(body);
        req.downloadHandler = new DownloadHandlerBuffer();
        req.SetRequestHeader("Content-Type", "application/json");

        var op = req.SendWebRequest();
        while (!op.isDone) await Task.Yield();

        if (req.result != UnityWebRequest.Result.Success)
        {
            Debug.LogError($"Pond API error: {req.error} {req.downloadHandler.text}");
            return $"Error: {req.error}";
        }
        return req.downloadHandler.text;
    }

    // ---------- buttons ----------
    public async void BeginRitual()
    {
        string json = $"{{\"session_id\":\"{sessionId}\",\"title\":\"{TitleField.text}\",\"offering\":\"{OfferingField.text}\"}}";
        string reply = await PostJson("/begin", json);
        ShowReply(reply);
    }

    public async void AdvanceRitual()
    {
        string json = $"{{\"session_id\":\"{sessionId}\",\"reply\":\"{ReplyField.text}\"}}";
        string reply = await PostJson("/advance", json);
        ShowReply(reply);
        ReplyField.text = "";
    }

    private void ShowReply(string json)
    {
        // crude extraction of "html" field for demo purposes
        int start = json.IndexOf("\"html\":\"") + 8;
        int end = json.IndexOf("\",\"finished\"");
        if (start > 0 && end > start)
        {
            string html = json.Substring(start, end - start)
                              .Replace("\\n", "\n")
                              .Replace("\\\"", "\"");
            OutputText.text = html;
        }
        else
        {
            OutputText.text = json;
        }
    }
}
