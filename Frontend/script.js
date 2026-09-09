const API_BASE = "https://0v2cnilfff.execute-api.us-east-1.amazonaws.com/prod";

async function processCV() {
    const fileInput = document.getElementById('cvFile');
    const jobDesc = document.getElementById('jobDesc').value.trim();

    if (!fileInput.files[0] || !jobDesc) {
        alert('يرجى اختيار ملف PDF وكتابة الوصف الوظيفي!');
        return;
    }

    const file = fileInput.files[0];
    showLoader("جاري رفع الملف والبدء بالتحليل...");

    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = async function () {
        const base64 = reader.result.split(',')[1];

        try {
            // 1. Upload
            const res = await fetch(`${API_BASE}/upload`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ file_content: base64, job_description: jobDesc })
            });

            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'فشل الرفع');

            // 2. Poll for results
            showLoader("جاري استخلاص النص وتحليل الكلمات بـ Comprehend NLP...");
            pollResults(data.cv_id);

        } catch (err) {
            alert(`خطأ: ${err.message}`);
            hideLoader();
        }
    };
}

async function pollResults(cvId) {
    let attempts = 0;
    const interval = setInterval(async () => {
        attempts++;
        try {
            const res = await fetch(`${API_BASE}/result?cv_id=${cvId}`);
            if (res.status === 200) {
                const data = await res.json();
                clearInterval(interval);
                showResults(data);
            } else if (attempts > 15) {
                clearInterval(interval);
                alert("استغرق التحليل وقتاً أطول من المتوقع، يرجى المحاولة لاحقاً.");
                hideLoader();
            }
        } catch (err) {
            console.error(err);
        }
    }, 3000); // Check every 3 seconds
}

function showResults(data) {
    hideLoader();
    document.getElementById('uploadForm').style.display = 'none';
    document.getElementById('resultsBox').style.display = 'block';

    const score = data.match_score || 0;
    const circle = document.getElementById('scoreCircle');
    circle.innerText = `${score}%`;

    if (score >= 70) circle.className = "score-circle score-good";
    else if (score >= 40) circle.className = "score-circle score-mid";
    else circle.className = "score-circle score-bad";

    const missingDiv = document.getElementById('missingKeywords');
    missingDiv.innerHTML = '';
    if (data.missing_keywords && data.missing_keywords.length > 0) {
        data.missing_keywords.forEach(kw => {
            missingDiv.innerHTML += `<span class="tag tag-missing">${kw}</span>`;
        });
    } else {
        missingDiv.innerHTML = '<span class="tag">ممتاز! السيرة الذاتية تغطي كافة المهارات الأساسية المطلوبة.</span>';
    }
}

function showLoader(text) {
    document.getElementById('uploadForm').style.display = 'none';
    document.getElementById('loader').style.display = 'block';
    document.getElementById('loaderText').innerText = text;
}

function hideLoader() {
    document.getElementById('loader').style.display = 'none';
}

function resetForm() {
    document.getElementById('resultsBox').style.display = 'none';
    document.getElementById('uploadForm').style.display = 'block';
    document.getElementById('cvFile').value = '';
    document.getElementById('jobDesc').value = '';
}