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

def should_crop(image):
    """Détermine si l'image doit être rognée ou non."""
    height, width = image.shape[:2]
    aspect_ratio = height / width
    # Si le rapport hauteur/largeur est plus grand que 1.3, on suppose que l'image est longue et doit être rognée
    return aspect_ratio > 1.3

def crop_to_face(image):
    """Rogne fortement pour capturer uniquement la partie supérieure (visage) pour les images longues."""
    height, width = image.shape[:2]
    
    if should_crop(image):
        # Rogner pour capturer seulement le haut de l'image, en supposant que le visage est dans les 25% supérieurs
        crop_top = int(height * 0.15)  # Ajuster la hauteur du début du rognage
        crop_bottom = int(height * 0.55)  # Rogner à 55% de la hauteur pour capturer juste le visage
        return image[crop_top:crop_bottom, :]
    else:
        return image  # Ne pas rogner

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

                # Rogner l'image pour se concentrer sur le visage si nécessaire
                cropped_image = crop_to_face(image)

                # Charger l'image de fond
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

                    # Redimensionner l'image téléchargée (rognée ou non) pour s'adapter à la zone noire
                    resized_image = cv2.resize(cropped_image, (w, h), interpolation=cv2.INTER_AREA)

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