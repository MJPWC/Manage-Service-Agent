/**
 * Shared auth / upload API calls used by login.js, github.js, and app.js (dashboard).
 * Loads before those scripts; exposes window.AuthApi.
 */
(function (global) {
  "use strict";

  function jsonPost(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (response) {
      return response.json().then(function (data) {
        return { ok: response.ok, status: response.status, data: data };
      });
    });
  }

  function formPost(url, formData) {
    return fetch(url, {
      method: "POST",
      body: formData,
    }).then(function (response) {
      return response.json().then(function (data) {
        return { ok: response.ok, status: response.status, data: data };
      });
    });
  }

  global.AuthApi = {
    postAnypointLogin: function (username, password) {
      return jsonPost("/api/anypoint/login", { username: username, password: password });
    },
    postConnectedAppLogin: function (payload) {
      return jsonPost("/api/connectedapp/login", payload);
    },
    postGithubLogin: function (username, token) {
      return jsonPost("/api/github/login", { username: username, token: token });
    },
    postLocalUpload: function (formData) {
      return formPost("/api/local/upload", formData);
    },

    /**
     * Same rules as login page local upload: .log / .txt only, max 50 MB.
     * @returns {{ ok: true } | { ok: false, message: string }}
     */
    validateLocalLogFile: function (file) {
      if (!file) {
        return { ok: false, message: "Please select a log file to upload." };
      }
      var allowed = [".log", ".txt"];
      var ext = "." + file.name.split(".").pop().toLowerCase();
      if (allowed.indexOf(ext) === -1) {
        return {
          ok: false,
          message: "Invalid file type. Only .log and .txt files are allowed.",
        };
      }
      var maxSize = 50 * 1024 * 1024;
      if (file.size > maxSize) {
        return {
          ok: false,
          message:
            "File too large (" +
            (file.size / 1024 / 1024).toFixed(1) +
            " MB). Maximum is 50 MB.",
        };
      }
      return { ok: true };
    },
  };
})(typeof window !== "undefined" ? window : this);
