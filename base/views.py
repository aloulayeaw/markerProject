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


# Create your views here.
def home(request):  

    return render(request, 'index.html')

def detect_face(image):
    """Détecte un visage dans l'image pour cibler correctement la figure."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    faces = face_cascade.detectMultiScale(gray, 1.1, 4)
    
    if len(faces) > 0:
        # Retourner le premier visage détecté
        (x, y, w, h) = faces[0]
        return (x, y, w, h)
    else:
        return None

def crop_and_resize_image(image, mask_width, mask_height):
    """Rogne et redimensionne l'image pour qu'elle s'adapte à la zone cible sans zoom excessif et sans étirer."""
    height, width = image.shape[:2]

    # Détecter le visage pour centrer l'image autour du visage
    face = detect_face(image)
    
    if face:
        (x, y, w, h) = face
        
        # Déterminer les bords de la zone à conserver
        crop_top = max(0, y - int(h * 0.5))  # Inclure un peu au-dessus du visage
        crop_bottom = min(height, y + int(h * 2))  # Inclure un peu en dessous du visage pour couvrir la figure
        
        cropped_image = image[crop_top:crop_bottom, :]
    else:
        # Si aucun visage n'est détecté, centrer sur la partie médiane de l'image
        crop_top = int(height * 0.15)
        crop_bottom = int(height * 0.85)
        cropped_image = image[crop_top:crop_bottom, :]

    # Ajuster le redimensionnement tout en conservant le ratio d'aspect
    aspect_ratio_image = cropped_image.shape[1] / cropped_image.shape[0]
    aspect_ratio_mask = mask_width / mask_height

    if aspect_ratio_image > aspect_ratio_mask:
        # Si l'image est plus large que le masque, ajuster selon la largeur
        new_width = mask_width
        new_height = int(new_width / aspect_ratio_image)
    else:
        # Si l'image est plus haute que le masque, ajuster selon la hauteur
        new_height = mask_height
        new_width = int(new_height * aspect_ratio_image)

    resized_image = cv2.resize(cropped_image, (new_width, new_height), interpolation=cv2.INTER_AREA)

    # Ajouter du padding si nécessaire pour que l'image s'adapte parfaitement au masque
    delta_w = mask_width - new_width
    delta_h = mask_height - new_height
    top, bottom = delta_h // 2, delta_h - (delta_h // 2)
    left, right = delta_w // 2, delta_w - (delta_w // 2)

    # Ajouter des bordures pour centrer l'image dans la zone du masque
    padded_image = cv2.copyMakeBorder(resized_image, top, bottom, left, right, cv2.BORDER_CONSTANT, value=[0, 0, 0])

    return padded_image

def overlay_photos(request):
    if request.method == 'POST':
        try:
            form = PhotoUploadForm(request.POST, request.FILES)
            if form.is_valid():
                uploaded_image = request.FILES['image']

                # Enregistrer le fichier téléchargé temporairement
                fs = FileSystemStorage()
                temp_image_path = fs.save(f'temp_{uploaded_image.name}', uploaded_image)
                temp_image_path = os.path.join(settings.MEDIA_ROOT, temp_image_path)

                # Charger l'image téléchargée
                image = cv2.imread(temp_image_path)

                if image is None or len(image.shape) not in [2, 3]:
                    fs.delete(temp_image_path)
                    return JsonResponse({'success': False, 'message': 'Invalid image format.'}, status=400)

                # Charger l'image de fond (contenant la zone noire circulaire)
                background_path = os.path.join(settings.BASE_DIR, 'image_marker.jpg')  # Chemin vers l'image de fond
                background = cv2.imread(background_path)

                # Traiter l'image de fond pour trouver la zone noire
                gray_background = cv2.cvtColor(background, cv2.COLOR_BGR2GRAY)
                _, mask = cv2.threshold(gray_background, 10, 255, cv2.THRESH_BINARY_INV)  # Détecter la zone noire

                # Trouver les contours dans la zone noire
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if contours:
                    cnt = max(contours, key=cv2.contourArea)
                    x, y, w, h = cv2.boundingRect(cnt)

                    # Rogner et redimensionner l'image téléchargée pour s'adapter à la zone noire sans étirement
                    resized_image = crop_and_resize_image(image, w, h)

                    # Créer un masque circulaire à appliquer sur l'image redimensionnée
                    radius = min(w, h) // 2
                    center = (w // 2, h // 2)
                    circular_mask = np.zeros((h, w, 4), dtype=np.uint8)
                    cv2.circle(circular_mask, center, radius, (255, 255, 255, 255), -1)

                    # Appliquer le masque circulaire sur l'image redimensionnée
                    resized_image_rgba = cv2.cvtColor(resized_image, cv2.COLOR_BGR2BGRA)
                    masked_image = cv2.bitwise_and(resized_image_rgba, circular_mask)

                    # Assurer la transparence là où était le noir dans le masque
                    alpha_mask = circular_mask[:, :, 3] / 255.0
                    alpha_inv = 1.0 - alpha_mask
                    for c in range(3):
                        background[y:y+h, x:x+w, c] = (alpha_mask * masked_image[:, :, c] +
                                                       alpha_inv * background[y:y+h, x:x+w, c])

                    # Convertir l'image finale au format JPEG puis en base64
                    _, buffer = cv2.imencode('.jpg', background)
                    image_base64 = base64.b64encode(buffer).decode('utf-8')

                    # Supprimer l'image téléchargée temporairement
                    fs.delete(temp_image_path)

                    # Retourner une réponse JSON avec l'image en base64
                    return JsonResponse({'success': True, 'result_image': image_base64})

                else:
                    fs.delete(temp_image_path)
                    return JsonResponse({'success': False, 'message': 'No contours found.'}, status=400)

            # Si le formulaire n'est pas valide
            return JsonResponse({'success': False, 'message': 'Invalid form data.'}, status=400)

        except Exception as e:
            # Retourner une réponse JSON en cas d'exception inattendue
            return JsonResponse({'success': False, 'message': str(e)}, status=500)

    elif request.method == 'GET':
        # Si c'est une requête GET, afficher le formulaire dans la page HTML
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