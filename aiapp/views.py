from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.conf import settings
from django.contrib import messages

import json
import os
import tempfile
import subprocess
from dotenv import load_dotenv
import google.generativeai as genai
load_dotenv()  # Loads .env into os.environ

api_key = os.getenv("GEMINI_API_KEY")
# Initialize Gemini client
genai.configure(api_key=api_key)

@login_required
def index(request):
    """Main dashboard page"""
    return render(request, 'dashboard.html')


def u_login(request):
    """User login view"""
    if request.user.is_authenticated:
        return redirect('/')
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        
        if not username or not password:
            messages.error(request, 'Please provide both username and password.')
            return render(request, 'login.html')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.GET.get('next', '/')
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'login.html')


def u_signup(request):
    """User registration view"""
    if request.user.is_authenticated:
        return redirect('/')
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        repassword = request.POST.get('repassword', '')
        
        # Validation
        if not all([username, email, password, repassword]):
            messages.error(request, 'All fields are required.')
            return render(request, 'signup.html')
        
        if len(username) < 3:
            messages.error(request, 'Username must be at least 3 characters long.')
            return render(request, 'signup.html')
        
        if len(password) < 6:
            messages.error(request, 'Password must be at least 6 characters long.')
            return render(request, 'signup.html')
        
        if password != repassword:
            messages.error(request, 'Passwords do not match.')
            return render(request, 'signup.html')
        
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
            return render(request, 'signup.html')
        
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered.')
            return render(request, 'signup.html')
        
        try:
            user = User.objects.create_user(username=username, email=email, password=password)
            user.save()
            login(request, user)
            messages.success(request, 'Account created successfully!')
            return redirect('/')
        except Exception as e:
            messages.error(request, 'Error creating account. Please try again.')
    
    return render(request, 'signup.html')


@login_required
def u_logout(request):
    """User logout view"""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('/login/')


def get_youtube_title(link):
    """Extract YouTube video title using yt-dlp"""
    try:
        # Use yt-dlp to get video info
        cmd = [
            'yt-dlp',
            '--get-title',
            '--no-warnings',
            link
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        else:
            print(f"yt-dlp title error: {result.stderr}")
            return "Untitled Video"
            
    except Exception as e:
        print(f"Error getting YouTube title: {e}")
        return "Untitled Video"


def download_youtube_audio(link):
    """Download YouTube video as audio file using yt-dlp"""
    try:
        # Create temporary directory for download
        temp_dir = tempfile.gettempdir()
        output_template = os.path.join(temp_dir, '%(title)s.%(ext)s')
        
        # Use yt-dlp to download audio
        cmd = [
            'yt-dlp',
            '-f', 'bestaudio/best',  # Get best audio quality
            '--extract-audio',       # Extract audio only
            '--audio-format', 'mp3', # Convert to mp3
            '--audio-quality', '192K', # Good quality
            '-o', output_template,   # Output template
            '--no-warnings',
            '--no-playlist',         # Don't download playlist
            link
        ]
        
        print(f"Running yt-dlp command: {' '.join(cmd)}")
        
        # Run the command
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)  # 5 minutes timeout
        
        if result.returncode != 0:
            print(f"yt-dlp error: {result.stderr}")
            return None
        
        # Find the downloaded file
        # yt-dlp creates files with the video title, so we need to find it
        for file in os.listdir(temp_dir):
            if file.endswith('.mp3') and any(char in file for char in link.split('/')[-1]):
                return os.path.join(temp_dir, file)
        
        # Alternative: look for recently created mp3 files
        import time
        mp3_files = []
        for file in os.listdir(temp_dir):
            if file.endswith('.mp3'):
                file_path = os.path.join(temp_dir, file)
                # Check if file was created in the last 10 minutes
                if time.time() - os.path.getctime(file_path) < 600:
                    mp3_files.append((file_path, os.path.getctime(file_path)))
        
        if mp3_files:
            # Return the most recently created mp3 file
            mp3_files.sort(key=lambda x: x[1], reverse=True)
            return mp3_files[0][0]
        
        print("No mp3 file found after download")
        return None
        
    except subprocess.TimeoutExpired:
        print("yt-dlp download timed out")
        return None
    except Exception as e:
        print(f"Error downloading audio: {e}")
        print(f"Error type: {type(e)}")
        return None


def transcribe_audio_with_gemini(audio_file_path):
    """Transcribe audio file using Google Gemini"""
    try:
        # Initialize the model
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        # Upload the audio file to Gemini
        audio_file = genai.upload_file(path=audio_file_path)
        
        # Wait for the file to be processed
        import time
        while audio_file.state.name == "PROCESSING":
            print("Processing audio file...")
            time.sleep(2)
            audio_file = genai.get_file(audio_file.name)
        
        if audio_file.state.name == "FAILED":
            print("Audio file processing failed")
            return None
        
        # Generate transcription
        prompt = "Please transcribe this audio file. Provide only the transcription text without any additional commentary."
        
        response = model.generate_content(
            [prompt, audio_file],
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=4000,
                temperature=0.1,
            )
        )
        
        # Clean up the uploaded file
        genai.delete_file(audio_file.name)
        
        return response.text.strip()
        
    except Exception as e:
        print(f"Error during Gemini transcription: {e}")
        return None


def generate_blog_content(transcription, blog_style="professional"):
    """Generate blog content from transcription using Google Gemini"""
    try:
        # Initialize the model
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        style_prompts = {
            "professional": "Write a professional, well-structured blog article",
            "casual": "Write a casual, conversational blog post",
            "technical": "Write a detailed, technical blog article",
            "creative": "Write an engaging, creative blog post"
        }
        
        style_instruction = style_prompts.get(blog_style, style_prompts["professional"])
        
        prompt = f"""You are a professional blog writer who creates engaging, well-structured articles.

{style_instruction} based on the following transcript. Make it engaging and don't make it feel like a transcript. Add proper headings, structure, and make it flow naturally:

{transcription}

Please ensure the blog post:
- Has a compelling title
- Is well-structured with clear headings
- Flows naturally and doesn't read like a transcript
- Is engaging and informative
- Has a proper conclusion"""

        # Generate content
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=2000,
                temperature=0.7,
            )
        )
        
        return response.text.strip()
    except Exception as e:
        print(f"Error generating blog with Gemini: {e}")
        return None


@csrf_exempt
def generate_blog(request):
    """Main blog generation endpoint"""
    if request.method != "POST":
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)
    
    # Check if user is authenticated
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    try:
        data = json.loads(request.body)
        yt_link = data.get('link', '').strip()
        blog_style = data.get('style', 'professional')
        
        if not yt_link:
            return JsonResponse({'error': 'YouTube link is required'}, status=400)
        
        # Validate YouTube URL
        if 'youtube.com/watch' not in yt_link and 'youtu.be/' not in yt_link:
            return JsonResponse({'error': 'Please provide a valid YouTube URL'}, status=400)
        
        # Step 1: Get video title
        title = get_youtube_title(yt_link)
        
        # Step 2: Download audio
        audio_file = download_youtube_audio(yt_link)
        if not audio_file:
            return JsonResponse({'error': 'Failed to download video audio'}, status=500)
        
        try:
            # Step 3: Transcribe audio using Gemini
            transcription = transcribe_audio_with_gemini(audio_file)
            if not transcription:
                return JsonResponse({'error': 'Failed to transcribe audio'}, status=500)
            
            # Step 4: Generate blog content
            blog_content = generate_blog_content(transcription, blog_style)
            if not blog_content:
                return JsonResponse({'error': 'Failed to generate blog content'}, status=500)
            
            return JsonResponse({
                'success': True,
                'title': title,
                'content': blog_content,
                'transcription': transcription,
                'word_count': len(blog_content.split())
            })
            
        finally:
            # Clean up temporary audio file
            if audio_file and os.path.exists(audio_file):
                try:
                    os.remove(audio_file)
                except:
                    pass
    
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        print(f"Unexpected error: {e}")
        return JsonResponse({'error': 'An unexpected error occurred'}, status=500)


# @login_required
# def blog_history(request):
#     """View for showing blog generation history (placeholder for future implementation)"""
#     return render(request, 'blog_history.html')


# def health_check(request):
#     """Simple health check endpoint"""
#     return JsonResponse({'status': 'healthy', 'message': 'Blog generator is running'})