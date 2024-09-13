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
import base64
import json
from datetime import datetime


# Create your views here.
def home(request):  

    return render(request, 'index.html')



# Fonction pour vérifier si l'image doit être rognée
def should_crop(image):
    """Détermine si l'image doit être rognée ou non."""
    height, width = image.shape[:2]
    aspect_ratio = height / width
    return aspect_ratio > 1.3

# Fonction pour vérifier si une personne est assise
def is_person_sitting(image):
    """Détecte si la personne est assise en se basant sur la proportion verticale occupée par la personne."""
    height, width = image.shape[:2]
    person_height = height * 0.6
    return person_height < height * 0.5

# Fonction pour rogner et centrer l'image avec un zoom modéré
def crop_and_center_image(image):
    """Rogne et centre l'image en fonction de si la personne est assise ou debout, avec un zoom modéré."""
    height, width = image.shape[:2]

    if should_crop(image):
        if is_person_sitting(image):
            crop_top = int(height * 0.10)  # Rogner légèrement le haut pour centrer le visage
            crop_bottom = int(height * 0.90)  # Garder la majeure partie de l'image
        else:
            crop_top = int(height * 0.05)  # Moins de rognage sur le haut
            crop_bottom = int(height * 0.95)  # Moins de rognage sur le bas
        cropped_image = image[crop_top:crop_bottom, :]
    else:
        cropped_image = image

    # Assurer que l'image est bien centrée
    desired_size = min(cropped_image.shape[1], cropped_image.shape[0])

    if cropped_image.shape[1] > cropped_image.shape[0]:
        padding = (cropped_image.shape[1] - desired_size) // 2
        centered_image = cropped_image[:, padding:padding + desired_size]
    else:
        padding = (cropped_image.shape[0] - desired_size) // 2
        centered_image = cropped_image[padding:padding + desired_size, :]

    return centered_image

# Fonction pour sauvegarder et mettre à jour le nombre de photos générées dans un fichier JSON
def update_photo_count():
    """Met à jour le fichier JSON pour enregistrer le nombre de photos générées par jour."""
    json_file = os.path.join(settings.BASE_DIR, 'photo_count.json')  # Chemin vers le fichier JSON
    today_date = datetime.now().strftime('%Y-%m-%d')

    # Si le fichier n'existe pas, créer un fichier vide
    if not os.path.exists(json_file):
        data = {}
    else:
        # Charger les données existantes du fichier JSON
        with open(json_file, 'r') as file:
            data = json.load(file)

    # Si la date d'aujourd'hui existe, incrémenter le compteur, sinon le créer
    if today_date in data:
        data[today_date] += 1
    else:
        data[today_date] = 1

    # Sauvegarder les données dans le fichier JSON
    with open(json_file, 'w') as file:
        json.dump(data, file)

    # Afficher le nombre de photos générées aujourd'hui
    print(f"Nombre de photos générées aujourd'hui ({today_date}): {data[today_date]}")

# Fonction principale pour traiter les images et superposer les photos
def overlay_photos(request):
    if request.method == 'POST':
        try:
            form = PhotoUploadForm(request.POST, request.FILES)
            if form.is_valid():
                uploaded_image = request.FILES['image']
                fs = FileSystemStorage()
                temp_image_path = fs.save(f'temp_{uploaded_image.name}', uploaded_image)
                temp_image_path = os.path.join(settings.MEDIA_ROOT, temp_image_path)

                image = cv2.imread(temp_image_path)
                if image is None or len(image.shape) not in [2, 3]:
                    fs.delete(temp_image_path)
                    return JsonResponse({'success': False, 'message': 'Invalid image format.'}, status=400)

                centered_image = crop_and_center_image(image)
                background_path = os.path.join(settings.BASE_DIR, 'image_marker.jpg')
                background = cv2.imread(background_path)

                gray_background = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)
                _, mask = cv2.threshold(gray_background, 10, 255, cv2.THRESH_BINARY_INV)
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                if contours:
                    cnt = max(contours, key=cv2.contourArea)
                    x, y, w, h = cv2.boundingRect(cnt)

                    resized_image = cv2.resize(centered_image, (w, h), interpolation=cv2.INTER_AREA)
                    radius = min(w, h) // 2
                    center = (w // 2, h // 2)
                    circular_mask = np.zeros((h, w, 4), dtype=np.uint8)
                    cv2.circle(circular_mask, center, radius, (255, 255, 255, 255), -1)

                    resized_image_rgba = cv2.cvtColor(resized_image, cv2.COLOR_BGR2BGRA)
                    masked_image = cv2.bitwise_and(resized_image_rgba, circular_mask)

                    alpha_mask = circular_mask[:, :, 3] / 255.0
                    alpha_inv = 1.0 - alpha_mask
                    for c in range(3):
                        background[y:y+h, x:x+w, c] = (alpha_mask * masked_image[:, :, c] +
                                                       alpha_inv * background[y:y+h, x:x+w, c])

                    _, buffer = cv2.imencode('.jpg', background)
                    image_base64 = base64.b64encode(buffer).decode('utf-8')

                    fs.delete(temp_image_path)
                    update_photo_count()

                    return JsonResponse({'success': True, 'result_image': image_base64})

                else:
                    fs.delete(temp_image_path)
                    return JsonResponse({'success': False, 'message': 'No contours found.'}, status=400)

            return JsonResponse({'success': False, 'message': 'Invalid form data.'}, status=400)

        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)

    elif request.method == 'GET':
        form = PhotoUploadForm()
        return render(request, 'base/upload.html', {'form': form})

    return JsonResponse({'success': False, 'message': 'Invalid request method.'}, status=400)

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