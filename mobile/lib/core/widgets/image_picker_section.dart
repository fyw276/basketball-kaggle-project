import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../utils/app_snackbar.dart';
import 'platform_image.dart';

/// Multi-image picker section for uploading garment or outfit images.
class ImagePickerSection extends StatefulWidget {
  final List<XFile> images;
  final ValueChanged<List<XFile>> onImagesChanged;
  final int maxImages;
  final String hintText;
  final bool allowMultiple;
  final String? selectedImageUrl;
  final String? selectedImageLabel;
  final VoidCallback? onSelectedImageRemoved;
  final bool showWardrobeOption;
  final VoidCallback? onWardrobeTap;

  const ImagePickerSection({
    super.key,
    required this.images,
    required this.onImagesChanged,
    this.maxImages = 10,
    this.hintText = '点击选择图片',
    this.allowMultiple = true,
    this.selectedImageUrl,
    this.selectedImageLabel,
    this.onSelectedImageRemoved,
    this.showWardrobeOption = true,
    this.onWardrobeTap,
  });

  @override
  State<ImagePickerSection> createState() => _ImagePickerSectionState();
}

class _ImagePickerSectionState extends State<ImagePickerSection> {
  final ImagePicker _picker = ImagePicker();

  Future<void> _pickImage(ImageSource source) async {
    try {
      // Multi-select is only supported for gallery; camera must use single capture.
      if (widget.allowMultiple && source == ImageSource.gallery) {
        final pickedFiles = await _picker.pickMultiImage(
          imageQuality: 85,
          maxWidth: 1200,
          maxHeight: 1200,
        );

        if (pickedFiles.isNotEmpty) {
          final remaining = widget.maxImages - widget.images.length;
          final toAdd = pickedFiles.take(remaining).toList();
          widget.onImagesChanged([...widget.images, ...toAdd]);
        }
      } else {
        final pickedFile = await _picker.pickImage(
          source: source,
          imageQuality: 85,
          maxWidth: 1200,
          maxHeight: 1200,
        );

        if (pickedFile != null) {
          widget.onImagesChanged([pickedFile]);
        }
      }
    } catch (e) {
      if (mounted) {
        showAppSnackBar(context, '选择图片失败：${userFacingApiError(e)}');
      }
    }
  }

  bool get _cameraSupported =>
      !kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.android ||
          defaultTargetPlatform == TargetPlatform.iOS);

  void _showImageSourceDialog() {
    final showWardrobe =
        widget.showWardrobeOption && widget.onWardrobeTap != null;

    showModalBottomSheet(
      context: context,
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            ListTile(
              leading: const Icon(Icons.photo_library),
              title: const Text('相册'),
              onTap: () {
                Navigator.pop(ctx);
                _pickImage(ImageSource.gallery);
              },
            ),
            ListTile(
              leading: const Icon(Icons.camera_alt),
              title: const Text('相机'),
              subtitle: _cameraSupported ? null : const Text('当前设备不支持拍照，请使用相册'),
              enabled: _cameraSupported,
              onTap: _cameraSupported
                  ? () {
                      Navigator.pop(ctx);
                      _pickImage(ImageSource.camera);
                    }
                  : null,
            ),
            if (showWardrobe)
              ListTile(
                leading: const Icon(Icons.checkroom),
                title: const Text('从衣橱选择'),
                onTap: () {
                  Navigator.pop(ctx);
                  widget.onWardrobeTap?.call();
                },
              ),
          ],
        ),
      ),
    );
  }

  void _removeImage(int index) {
    final newImages = List<XFile>.from(widget.images);
    newImages.removeAt(index);
    widget.onImagesChanged(newImages);
  }

  @override
  Widget build(BuildContext context) {
    final hasSelectedImageUrl =
        widget.selectedImageUrl != null && widget.selectedImageUrl!.isNotEmpty;
    final selectedCount = widget.images.length + (hasSelectedImageUrl ? 1 : 0);
    final canAddMore = selectedCount < widget.maxImages;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Image preview grid
        if (selectedCount > 0)
          Container(
            height: 100,
            margin: const EdgeInsets.only(bottom: 12),
            child: ListView.builder(
              scrollDirection: Axis.horizontal,
              itemCount: selectedCount,
              itemBuilder: (context, index) {
                if (hasSelectedImageUrl && index == 0) {
                  return Padding(
                    padding: const EdgeInsets.only(right: 8),
                    child: Stack(
                      children: [
                        ClipRRect(
                          borderRadius: BorderRadius.circular(12),
                          child: SizedBox(
                            width: 100,
                            height: 100,
                            child: PlatformImage(
                              networkUrl: widget.selectedImageUrl!,
                              fit: BoxFit.cover,
                              errorWidget: Container(
                                width: 100,
                                height: 100,
                                color: Colors.grey.shade200,
                                child: const Icon(Icons.broken_image,
                                    color: Colors.grey),
                              ),
                            ),
                          ),
                        ),
                        if (widget.selectedImageLabel != null &&
                            widget.selectedImageLabel!.isNotEmpty)
                          Positioned(
                            left: 6,
                            bottom: 6,
                            child: Container(
                              padding: const EdgeInsets.symmetric(
                                  horizontal: 6, vertical: 3),
                              decoration: BoxDecoration(
                                color: Colors.black.withValues(alpha: 0.55),
                                borderRadius: BorderRadius.circular(7),
                              ),
                              child: Text(
                                widget.selectedImageLabel!,
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 10,
                                ),
                              ),
                            ),
                          ),
                        if (widget.onSelectedImageRemoved != null)
                          Positioned(
                            top: 4,
                            right: 4,
                            child: GestureDetector(
                              onTap: widget.onSelectedImageRemoved,
                              child: Container(
                                padding: const EdgeInsets.all(4),
                                decoration: BoxDecoration(
                                  color: Colors.black.withValues(alpha: 0.6),
                                  shape: BoxShape.circle,
                                ),
                                child: const Icon(
                                  Icons.close,
                                  size: 16,
                                  color: Colors.white,
                                ),
                              ),
                            ),
                          ),
                      ],
                    ),
                  );
                }
                final imageIndex = hasSelectedImageUrl ? index - 1 : index;
                final xfile = widget.images[imageIndex];
                return Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: Stack(
                    children: [
                      ClipRRect(
                        borderRadius: BorderRadius.circular(12),
                        child: SizedBox(
                          width: 100,
                          height: 100,
                          child: PlatformImage(
                            xfile: xfile,
                            fit: BoxFit.cover,
                            errorWidget: Container(
                              width: 100,
                              height: 100,
                              color: Colors.grey.shade200,
                              child: const Icon(Icons.broken_image,
                                  color: Colors.grey),
                            ),
                          ),
                        ),
                      ),
                      Positioned(
                        top: 4,
                        right: 4,
                        child: GestureDetector(
                          onTap: () => _removeImage(imageIndex),
                          child: Container(
                            padding: const EdgeInsets.all(4),
                            decoration: BoxDecoration(
                              color: Colors.black.withValues(alpha: 0.6),
                              shape: BoxShape.circle,
                            ),
                            child: const Icon(
                              Icons.close,
                              size: 16,
                              color: Colors.white,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                );
              },
            ),
          ),

        // Add button
        if (canAddMore)
          InkWell(
            onTap: _showImageSourceDialog,
            borderRadius: BorderRadius.circular(12),
            child: Container(
              height: 100,
              decoration: BoxDecoration(
                border: Border.all(
                  color: Theme.of(context)
                      .colorScheme
                      .outline
                      .withValues(alpha: 0.5),
                  width: 2,
                  style: BorderStyle.solid,
                ),
                borderRadius: BorderRadius.circular(12),
                color: Theme.of(context)
                    .colorScheme
                    .surfaceContainerHighest
                    .withValues(alpha: 0.3),
              ),
              child: Center(
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      Icons.add_photo_alternate_outlined,
                      size: 32,
                      color: Theme.of(context).colorScheme.primary,
                    ),
                    const SizedBox(height: 8),
                    Text(
                      widget.hintText,
                      style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                            color:
                                Theme.of(context).colorScheme.onSurfaceVariant,
                          ),
                    ),
                  ],
                ),
              ),
            ),
          ),

        // Image count indicator
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(
            '$selectedCount / ${widget.maxImages} 张图片',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
          ),
        ),
      ],
    );
  }
}
