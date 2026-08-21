import io
import os
from django.conf import settings
from django.core.files.base import ContentFile


def generate_qr_code(link) -> None:
    """
    Generate a QR code image for a link and save it to the link's qr_code field.
    
    Uses the qrcode library to generate a QR code that points to the short URL.
    The image is stored as a PNG file associated with the link.
    
    Args:
        link: The Link instance to generate a QR code for
    """
    try:
        import qrcode
        from qrcode.image.styledpil import StyledPilImage
        from qrcode.image.styles.moduledrawers import RoundedModuleDrawer
        from qrcode.image.styles.colormasks import SolidFillColorMask
    except ImportError:
        _generate_simple_qr(link)
        return
    
    try:
        short_url = link.get_short_url()
        
        # Create QR code instance with better styling
        qr = qrcode.QRCode(
            version=None,  # Auto-size
            error_correction=qrcode.constants.ERROR_CORRECT_M,  # Medium error correction
            box_size=10,
            border=2,
        )
        qr.add_data(short_url)
        qr.make(fit=True)
        
        # Create styled image with rounded modules and primary color
        primary_color = (99, 102, 241)  # #6366F1
        
        qr_image = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=RoundedModuleDrawer(),
            color_mask=SolidFillColorMask(
                front_color=primary_color,
                back_color=(255, 255, 255),
            ),
        )
        
        # Convert to PNG bytes
        buffer = io.BytesIO()
        qr_image.save(buffer, format='PNG', optimize=True)
        
        # Save to the link's qr_code field
        filename = f"qr_{link.slug}.png"
        link.qr_code.save(filename, ContentFile(buffer.getvalue()), save=False)
        link.save(update_fields=['qr_code'])
    except Exception:
        # Fallback to simple QR if styling fails
        _generate_simple_qr(link)


def _generate_simple_qr(link) -> None:
    """
    Fallback QR code generation using basic qrcode.
    
    Args:
        link: The Link instance to generate a QR code for
    """
    try:
        import qrcode
        
        short_url = link.get_short_url()
        qr = qrcode.make(short_url)
        
        buffer = io.BytesIO()
        qr.save(buffer, format='PNG')
        
        filename = f"qr_{link.slug}.png"
        link.qr_code.save(filename, ContentFile(buffer.getvalue()), save=False)
        link.save(update_fields=['qr_code'])
    except Exception:
        # Silently fail - QR code is optional
        pass


def regenerate_qr_code(link) -> None:
    """
    Regenerate the QR code for a link (e.g., when the slug doesn't change
    but the link was updated).
    
    Args:
        link: The Link instance to regenerate QR for
    """
    # Delete old QR code if it exists
    if link.qr_code:
        old_path = link.qr_code.path
        if os.path.isfile(old_path):
            os.remove(old_path)
        link.qr_code = None
    
    generate_qr_code(link)
