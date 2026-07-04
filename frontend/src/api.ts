// Central API helper
const API = "/api";

function apiRequest(method: string, path: string, body?: any): Promise<any> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const token = localStorage.getItem("token") || "";
    xhr.open(method, API + path);
    xhr.setRequestHeader("Authorization", "Bearer " + token);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.onload = () => { try { resolve(JSON.parse(xhr.responseText)); } catch { reject(new Error("Parse error")); } };
    xhr.onerror = () => reject(new Error("Network error"));
    xhr.send(body ? JSON.stringify(body) : null);
  });
}

export function apiLogin(email: string, password: string): Promise<any> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", API + "/auth/login");
    xhr.setRequestHeader("Content-Type", "application/x-www-form-urlencoded");
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) { try { resolve(JSON.parse(xhr.responseText)); } catch { reject(new Error("Parse error")); } }
      else { reject(new Error("Login failed: " + xhr.status)); }
    };
    xhr.onerror = () => reject(new Error("Network error"));
    xhr.send("username=" + encodeURIComponent(email) + "&password=" + encodeURIComponent(password));
  });
}

export function apiGet(path: string) { return apiRequest("GET", path); }
export function apiPost(path: string, body: any) { return apiRequest("POST", path, body); }

// Click-to-call through the Yeastar PBX (proxied by the backend, which holds the PBX
// credentials/token). Rings the agent extension first, then dials the number.
// Returns the PBX result {ok, caller, errcode, errmsg} so the UI can show what happened.
export async function placeCall(phone: string): Promise<any> {
  const extension = localStorage.getItem("yeastarExtension") || "";
  try {
    const res = await apiPost("/dialer/call", { phone, extension });
    return res || { ok: false, errmsg: "No response from server" };
  } catch {
    return { ok: false, errmsg: "Network error reaching the server" };
  }
}
export function apiPatch(path: string, body: any) { return apiRequest("PATCH", path, body); }
export function apiPut(path: string, body: any) { return apiRequest("PUT", path, body); }
export function apiDelete(path: string) { return apiRequest("DELETE", path); }
export default API;
