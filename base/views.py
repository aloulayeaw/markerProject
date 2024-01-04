from django.shortcuts import render
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import render, redirect
from .forms import PhotoUploadForm
import cv2
import numpy as np
from django.core.files.storage import FileSystemStorage
from django.conf import settings
import os
import numpy as np

# Create your views here.
def home(request):  

    return render(request, 'index.html')

def overlay_photos(request):
    if request.method == 'POST':
        form = PhotoUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_image = request.FILES['image']

            # Save the uploaded file to a temporary location
            fs = FileSystemStorage()
            temp_image_path = fs.save('temp_' + uploaded_image.name, uploaded_image)
            temp_image_path = os.path.join(settings.MEDIA_ROOT, temp_image_path)

            # Load the uploaded image using OpenCV
            image = cv2.imread(temp_image_path, cv2.IMREAD_UNCHANGED)

            # Load the background image from a specific path
            background_path = 'D:/data/image_marker.jpeg'
            background = cv2.imread(background_path)

            # Convert the background image to grayscale and find the white area
            gray_background = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)
            _, mask = cv2.threshold(gray_background, 250, 255, cv2.THRESH_BINARY)

            # Find the contours of the white area
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if contours:
                # Assume the largest contour is the white area
                cnt = max(contours, key=cv2.contourArea)
                x, y, w, h = cv2.boundingRect(cnt)

                # Use the Haar Cascade face detector to find the head in the uploaded image
                face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
                faces = face_cascade.detectMultiScale(image, scaleFactor=1.1, minNeighbors=7, minSize=(40, 40))

                if len(faces) > 0:
                    # If at least one face is found, take the first (largest)
                    face_x, face_y, face_w, face_h = faces[0]

                    # Extract the head region from the image
                    head = image[face_y:face_y + face_h, face_x:face_x + face_w]

                    # Create a circular mask with transparency
                    radius = min(head.shape[0], head.shape[1]) // 2
                    center = (head.shape[1] // 2, head.shape[0] // 2)
                    circular_mask = np.zeros((head.shape[0], head.shape[1], 4), dtype=np.uint8)
                    cv2.circle(circular_mask, center, radius, (255, 255, 255, 255), -1)

                    # Apply the mask to get a circular head with transparency
                    head_rgba = cv2.cvtColor(head, cv2.COLOR_BGR2BGRA)
                    circular_head = cv2.bitwise_and(head_rgba, circular_mask)

                    # Resize the circular head to fill the white area
                    circular_head_resized = cv2.resize(circular_head, (w, h), interpolation=cv2.INTER_AREA)

                    # Blend the circular head with the background
                    alpha_mask = circular_head_resized[:, :, 3] / 255.0
                    alpha_inv = 1.0 - alpha_mask
                    head_color = circular_head_resized[:, :, :3]
                    bg_area = background[y:y+h, x:x+w]

                    for c in range(0, 3):
                        bg_area[:, :, c] = (alpha_mask * head_color[:, :, c] + alpha_inv * bg_area[:, :, c])

                    background[y:y+h, x:x+w] = bg_area

                # Define the destination path for the result
                result_image_path = 'D:/Dev/markerProject/temp/result.jpg'

                # Save the result to the specified directory
                cv2.imwrite(result_image_path, background)

                # Delete the temporary files
                fs.delete(temp_image_path)

                return JsonResponse({'success': True, 'message': 'Circular head placed in the white area successfully.', 'result_image': result_image_path})
            else:
                return JsonResponse({'success': False, 'message': 'No white area found or image invalid.'})
        else:
            return JsonResponse({'success': False, 'message': 'Invalid form.'})
    else:
        form = PhotoUploadForm()
    return render(request, 'base/upload.html', {'form': form})


def contact(request):
    if request.method == 'POST':
        name = request.POST.get('Name')
        email = request.POST.get('Email')
        phone = request.POST.get('phone')
        message = request.POST.get('message')

        if name and email and phone and message:
            
            subject = 'Nouveau message de contact'
            message_text = f'Nom: {name}\nEmail: {email}\nTéléphone: {phone}\nMessage: {message}'
            from_email = 'mamerane1003@gmail.com'
            recipient_list = ['mamerane1003@gmail.com']

            try:
                send_mail(subject, message_text, from_email, recipient_list, fail_silently=False)
                response_data = {'success': True, 'message': 'Les données ont été envoyées avec succès.'}
                return JsonResponse(response_data)
            except Exception as e:
                response_data = {'success': False, 'message': 'Une erreur s\'est produite lors de l\'envoi de votre message.'}
                return JsonResponse(response_data, status=500)
        else:
            response_data = {'success': False, 'message': 'Veuillez remplir tous les champs du formulaire.'}
            return JsonResponse(response_data, status=400)

    return render(request, 'index.html')