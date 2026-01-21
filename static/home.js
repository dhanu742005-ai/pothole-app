// Modern Upload Logic with Drag & Drop and Preview

document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');
    const uploadContent = document.getElementById('uploadContent');
    const previewContent = document.getElementById('previewContent');
    const imagePreview = document.getElementById('imagePreview');
    const fileName = document.getElementById('fileName');
    const removeBtn = document.getElementById('removeBtn');
    const submitBtn = document.getElementById('submitBtn');
    const uploadForm = document.getElementById('uploadForm');
    const loadingState = document.getElementById('loadingState');
    const locationStatus = document.getElementById('locationStatus');

    // Drag & Drop Events
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => {
            dropZone.classList.add('dragover');
        }, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => {
            dropZone.classList.remove('dragover');
        }, false);
    });

    // Handle File Drop
    dropZone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFiles(files);
    });

    // Handle Click to Upload
    dropZone.addEventListener('click', () => {
        if (!fileInput.value) {
            fileInput.click();
        }
    });

    fileInput.addEventListener('change', function () {
        handleFiles(this.files);
    });

    // File Processing
    function handleFiles(files) {
        if (files.length > 0) {
            const file = files[0];

            if (!file.type.startsWith('image/')) {
                alert('Please upload an image file (JPG, PNG).');
                return;
            }

            // Show Preview
            const reader = new FileReader();
            reader.onload = (e) => {
                imagePreview.src = e.target.result;
                fileName.textContent = file.name;

                uploadContent.classList.add('hidden');
                previewContent.classList.remove('hidden');
                submitBtn.classList.add('active');
                submitBtn.removeAttribute('disabled');
            };
            reader.readAsDataURL(file);
        }
    }

    // Remove File
    removeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        fileInput.value = '';
        uploadContent.classList.remove('hidden');
        previewContent.classList.add('hidden');
        submitBtn.classList.remove('active');
        submitBtn.setAttribute('disabled', 'true');
    });

    // Geolocation Handling
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            (position) => {
                document.getElementById('latitude').value = position.coords.latitude;
                document.getElementById('longitude').value = position.coords.longitude;
                updateLocationStatus(true);
            },
            (error) => {
                console.error("GPS Error:", error);
                updateLocationStatus(false);
            }
        );
    } else {
        updateLocationStatus(false);
    }

    function updateLocationStatus(success) {
        if (success) {
            locationStatus.querySelector('span').textContent = 'Location Attached';
            locationStatus.classList.add('active');
            locationStatus.querySelector('svg').style.color = '#38ef7d';
        } else {
            locationStatus.querySelector('span').textContent = 'Location Disabled';
            locationStatus.style.opacity = '0.7';
        }
    }

    // Form Submission Animation
    uploadForm.addEventListener('submit', (e) => {
        if (fileInput.files.length === 0) {
            e.preventDefault();
            return;
        }

        // Show loading state
        previewContent.classList.add('hidden');
        loadingState.classList.remove('hidden');
        submitBtn.innerHTML = '<span>Processing...</span><div class="spinner-sm"></div>';

        // Let form submit naturally
    });
});
