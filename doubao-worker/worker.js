const DEFAULT_ALLOWED_ORIGIN = "https://yz6953807-cmd.github.io";
const ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3";

function corsHeaders(env) {
  return {
    "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN || DEFAULT_ALLOWED_ORIGIN,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400"
  };
}

function json(data, status, env) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      ...corsHeaders(env),
      "Content-Type": "application/json; charset=utf-8"
    }
  });
}

function trimText(value, maxLength) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text;
}

export default {
  async fetch(request, env) {
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders(env) });
    }

    const url = new URL(request.url);
    if (request.method !== "POST" || url.pathname !== "/chat") {
      return json({ error: "Use POST /chat" }, 404, env);
    }

    if (!env.ARK_API_KEY || !env.ARK_MODEL) {
      return json({ error: "Missing ARK_API_KEY or ARK_MODEL on the worker." }, 500, env);
    }

    let payload;
    try {
      payload = await request.json();
    } catch {
      return json({ error: "Invalid JSON body." }, 400, env);
    }

    const message = trimText(payload.message, 900);
    const context = trimText(payload.context, 4200);
    const history = Array.isArray(payload.history) ? payload.history.slice(-6) : [];

    if (!message) {
      return json({ error: "Message is required." }, 400, env);
    }

    const messages = [
      {
        role: "system",
        content:
          "你是每日全球资讯简报网页里的毒舌小兔监督员。你要用中文回答，准确、简洁、有依据，优先结合用户当前简报上下文。语气可爱、犀利、轻微挖苦，但不要人身攻击、仇恨、恐吓或编造事实。涉及不确定内容要明确说明。回答长度一般控制在 150-450 字。"
      },
      {
        role: "user",
        content: `当前简报上下文：\n${context || "无"}`
      },
      ...history
        .filter((item) => item && (item.role === "user" || item.role === "assistant") && item.content)
        .map((item) => ({
          role: item.role,
          content: trimText(item.content, 700)
        })),
      {
        role: "user",
        content: message
      }
    ];

    const arkResponse = await fetch(`${ARK_BASE_URL}/chat/completions`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.ARK_API_KEY}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        model: env.ARK_MODEL,
        messages,
        temperature: Number(env.ARK_TEMPERATURE || 0.65),
        max_tokens: Number(env.ARK_MAX_TOKENS || 900)
      })
    });

    if (!arkResponse.ok) {
      const detail = await arkResponse.text();
      return json({ error: "Doubao request failed.", detail: trimText(detail, 800) }, 502, env);
    }

    const data = await arkResponse.json();
    const reply = data?.choices?.[0]?.message?.content || "";
    return json({
      reply,
      model: env.ARK_MODEL,
      source: "https://www.volcengine.com/product/ark"
    }, 200, env);
  }
};
