import client from "./client";

export async function login(id, pw) {
  const { data } = await client.post("/api/auth/login", { id, pw });
  return data;
}

export async function refreshToken(token) {
  const { data } = await client.post("/api/auth/refresh", {
    refresh_token: token,
  });
  return data;
}

export async function createDownload(url, resolution = "best") {
  const { data } = await client.post("/api/downloads", { url, resolution });
  return data;
}

export async function getHistory(skip = 0, limit = 20) {
  const { data } = await client.get("/api/downloads/history", {
    params: { skip, limit },
  });
  return data;
}

export async function deleteHistory(id) {
  await client.delete(`/api/downloads/history/${id}`);
}

export async function downloadFile(id) {
  const response = await client.get(`/api/files/${id}`, {
    responseType: "blob",
  });
  const contentDisposition = response.headers["content-disposition"];
  let filename = "download";
  if (contentDisposition) {
    const match = contentDisposition.match(/filename="?(.+?)"?$/);
    if (match) filename = match[1];
  }
  const url = window.URL.createObjectURL(response.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);
}
