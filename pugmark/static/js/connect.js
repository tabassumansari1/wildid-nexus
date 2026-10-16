(function () {
  var form = document.getElementById("scan-form");
  var input = document.getElementById("files");
  var list = document.getElementById("file-list");
  var submit = document.getElementById("submit");
  var hint = document.getElementById("hint");
  var drop = document.getElementById("drop");
  var overlay = document.getElementById("overlay");
  var errorBox = document.getElementById("form-error");
  var progress = document.getElementById("upload-progress");
  var progressLabel = document.getElementById("progress-label");
  var progressDetail = document.getElementById("progress-detail");
  var sampleData = document.getElementById("sample-data");
  if (!form || !input) return;

  var previewUrls = [];
  var imageExtensions = /\.(jpg|jpeg|png|webp|bmp|tif|tiff)$/i;
  var videoExtensions = /\.(mp4|mov|m4v|avi|webm|mkv)$/i;
  var maxFileBytes = 40 * 1024 * 1024;
  var maxTotalBytes = 160 * 1024 * 1024;
  var maxFiles = 12;

  var packs = {};
  try {
    packs = JSON.parse(sampleData.textContent);
  } catch {
    packs = {};
  }

  function csrf() {
    var match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function showError(message) {
    if (!errorBox) return;
    errorBox.hidden = false;
    errorBox.textContent = message;
  }

  function validate(files) {
    if (files.length < 2) return "Add at least two photos or videos.";
    if (files.length > maxFiles) return "Choose up to 12 files at a time.";
    var total = 0;
    for (var i = 0; i < files.length; i += 1) {
      var file = files[i];
      if (!imageExtensions.test(file.name) && !videoExtensions.test(file.name)) {
        return file.name + " is not a supported photo or video.";
      }
      if (file.size > maxFileBytes) return file.name + " is larger than 40 MB.";
      total += file.size;
    }
    if (total > maxTotalBytes) return "That set is larger than 160 MB. Split it into a smaller batch.";
    return "";
  }

  function clearPreviews() {
    previewUrls.forEach(function (url) { URL.revokeObjectURL(url); });
    previewUrls = [];
  }

  function render() {
    var files = Array.prototype.slice.call(input.files || []);
    clearPreviews();
    list.textContent = "";
    if (!files.length) {
      list.hidden = true;
    } else {
      list.hidden = false;
      files.forEach(function (file, index) {
        var item = document.createElement("li");
        var previewUrl = URL.createObjectURL(file);
        previewUrls.push(previewUrl);
        var preview;
        if (videoExtensions.test(file.name)) {
          preview = document.createElement("video");
          preview.muted = true;
          preview.playsInline = true;
          preview.preload = "metadata";
          preview.setAttribute("aria-label", "Video preview of " + file.name);
        } else {
          preview = document.createElement("img");
          preview.alt = "Preview of " + file.name;
        }
        preview.className = "file-preview";
        preview.src = previewUrl;
        var name = document.createElement("span");
        name.textContent = file.name;
        var meta = document.createElement("small");
        meta.textContent = videoExtensions.test(file.name) ? "Video" : "Photo";
        var remove = document.createElement("button");
        remove.type = "button";
        remove.textContent = "Remove";
        remove.setAttribute("aria-label", "Remove " + file.name);
        remove.addEventListener("click", function () {
          var next = new DataTransfer();
          files.forEach(function (candidate, candidateIndex) {
            if (candidateIndex !== index) next.items.add(candidate);
          });
          input.files = next.files;
          render();
        });
        item.appendChild(preview);
        item.appendChild(name);
        item.appendChild(meta);
        item.appendChild(remove);
        list.appendChild(item);
      });
    }
    var error = validate(files);
    submit.disabled = Boolean(error);
    hint.textContent = error || files.length + " files ready.";
    if (errorBox) errorBox.hidden = true;
  }

  input.addEventListener("change", render);

  ["dragenter", "dragover"].forEach(function (name) {
    drop.addEventListener(name, function (event) {
      event.preventDefault();
      drop.classList.add("is-hot");
    });
  });
  ["dragleave", "drop"].forEach(function (name) {
    drop.addEventListener(name, function (event) {
      event.preventDefault();
      drop.classList.remove("is-hot");
    });
  });
  drop.addEventListener("drop", function (event) {
    if (!event.dataTransfer || !event.dataTransfer.files.length) return;
    input.files = event.dataTransfer.files;
    render();
  });

  document.querySelectorAll("[data-pack]").forEach(function (button) {
    button.addEventListener("click", function () {
      var urls = packs[button.getAttribute("data-pack")] || [];
      button.disabled = true;
      Promise.all(
        urls.map(function (url) {
          return fetch(url).then(function (response) {
            if (!response.ok) throw new Error("Sample failed to load.");
            return response.blob().then(function (blob) {
              var name = url.split("/").pop();
              return new File([blob], name, { type: blob.type || "image/jpeg" });
            });
          });
        })
      )
        .then(function (files) {
          var next = new DataTransfer();
          files.forEach(function (file) { next.items.add(file); });
          input.files = next.files;
          render();
        })
        .catch(function () {
          showError("Could not load the sample set. Check that you opened Pugmark from its own address.");
        })
        .then(function () {
          button.disabled = false;
        });
    });
  });

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var files = Array.prototype.slice.call(input.files || []);
    var validationError = validate(files);
    if (validationError) {
      showError(validationError);
      return;
    }
    overlay.hidden = false;
    if (errorBox) errorBox.hidden = true;
    submit.disabled = true;
    progress.value = 0;
    progressLabel.textContent = "Uploading evidence.";
    progressDetail.textContent = "Your files stay in this local demonstration.";

    var request = new XMLHttpRequest();
    request.open("POST", form.action);
    request.responseType = "json";
    request.setRequestHeader("X-Requested-With", "XMLHttpRequest");
    request.setRequestHeader("X-CSRFToken", csrf());
    request.upload.addEventListener("progress", function (progressEvent) {
      if (!progressEvent.lengthComputable) return;
      var percent = Math.round((progressEvent.loaded / progressEvent.total) * 100);
      progress.value = percent;
      progressDetail.textContent = percent + "% uploaded. Preparing marking comparisons.";
    });
    request.upload.addEventListener("load", function () {
      progress.value = 100;
      progressLabel.textContent = "Comparing coat geometry.";
      progressDetail.textContent = "Upload complete. Checking marking points against one geometric transform.";
    });
    request.addEventListener("load", function () {
      var data = request.response;
      if (data && data.report_url && (request.status < 400 || request.status === 422)) {
        window.location.assign(data.report_url);
        return;
      }
      overlay.hidden = true;
      submit.disabled = false;
      showError((data && data.error) || "Could not compare these files.");
    });
    request.addEventListener("error", function () {
      overlay.hidden = true;
      submit.disabled = false;
      showError("The upload could not reach the analysis service. Check that it is running and try again.");
    });
    request.send(new FormData(form));
  });
})();
