// Central API helper
const API = "/api";

function apiRequest(method: string, path: string, body?: any): Promise<any> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const token = localStorage.getItem("token") || "";
    xhr.open(method, API + path);
    xhr.setRequestHeader("Authorization", "Bearer " + token);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.onload = () => {
      // Session expired (8h JWT / password change): don't leave the app showing zeros —
      // clear the dead token and return to the login screen.
      if (xhr.status === 401) {
        if (localStorage.getItem("token")) {
          localStorage.removeItem("token");
          window.location.reload();
        }
        reject(new Error("Session expired — please log in again"));
        return;
      }
      let parsed: any = null;
      try { parsed = JSON.parse(xhr.responseText); } catch { /* non-JSON body */ }
      if (xhr.status >= 200 && xhr.status < 300) {
        if (parsed === null) { reject(new Error("Parse error")); return; }
        resolve(parsed);
      } else {
        // real error responses must REJECT (previously any 4xx/5xx body resolved as
        // success — silent failed saves and pages rendering error objects)
        const msg = (parsed && (parsed.detail || parsed.error || parsed.message)) || ("HTTP " + xhr.status);
        reject(new Error(typeof msg === "string" ? msg : "Request failed"));
      }
    };
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

// Normalise a number for a device (tel:) call. Linkus / the Yeastar outbound route will NOT dial
// a "+" (E.164) number — it needs the international access prefix "00" instead. This mirrors the
// backend yeastar_service.dial() normalisation so a "Regular call (device)" dials the same as a
// PBX call.  +9647... -> 009647...   9647... -> 009647...   009647... -> unchanged
export function dialNumber(phone: string): string {
  const digits = String(phone || "").replace(/[^\d+]/g, "").replace(/^\++/, "");
  if (!digits) return "";
  return digits.startsWith("00") ? digits : "00" + digits;
}

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
// Click an IB name anywhere (Leads / Clients / Transactions / Trading accounts): the FIRST click
// filters that page's table; the SECOND click (this) opens the IB's profile — but ONLY if the IB
// is "under" the caller. The backend /ibs/access applies the same team-scope rule as the IB list,
// so a team leader can open their own IBs and is told "not yours" for anyone else's.
export async function openIbProfile(name: string): Promise<void> {
  try {
    const r = await apiGet(`/ibs/access?name=${encodeURIComponent(name)}`);
    if (r && r.can_view && r.ib_id) {
      window.dispatchEvent(new CustomEvent("navigate", { detail: { page: "ib_admin", ibId: r.ib_id } }));
    } else if (r && r.reason === "not_found") {
      window.alert(`No IB found for "${name}".`);
    } else {
      window.alert(`You can't open "${name}" — this IB is not in your team.`);
    }
  } catch {
    window.alert("Couldn't check IB access. Please try again.");
  }
}

export function apiPatch(path: string, body: any) { return apiRequest("PATCH", path, body); }
export function apiPut(path: string, body: any) { return apiRequest("PUT", path, body); }
export function apiDelete(path: string) { return apiRequest("DELETE", path); }
export default API;
