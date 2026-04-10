import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

/// 跨平台图片加载组件。
/// - 有网络 URL → Image.network
/// - 有本地 File/XFile 路径 → 平台适配加载
/// - 都无 → 占位图
class PlatformImage extends StatefulWidget {
  final String? networkUrl;
  final String? localPath;
  final XFile? xfile;
  final double? width;
  final double? height;
  final BoxFit fit;
  final Widget? placeholder;
  final Widget? errorWidget;

  const PlatformImage({
    super.key,
    this.networkUrl,
    this.localPath,
    this.xfile,
    this.width,
    this.height,
    this.fit = BoxFit.cover,
    this.placeholder,
    this.errorWidget,
  });

  @override
  State<PlatformImage> createState() => _PlatformImageState();
}

class _PlatformImageState extends State<PlatformImage> {
  Uint8List? _bytes;
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _maybeLoadLocal();
  }

  @override
  void didUpdateWidget(PlatformImage old) {
    super.didUpdateWidget(old);
    if (old.networkUrl != widget.networkUrl ||
        old.localPath != widget.localPath ||
        old.xfile != widget.xfile) {
      _maybeLoadLocal();
    }
  }

  Future<void> _maybeLoadLocal() async {
    // 如果没有网络 URL，尝试加载本地
    if (widget.networkUrl != null && widget.networkUrl!.isNotEmpty) return;

    if (widget.xfile != null) {
      await _loadXFile(widget.xfile!);
    } else if (widget.localPath != null && widget.localPath!.isNotEmpty) {
      await _loadLocalPath(widget.localPath!);
    }
  }

  Future<void> _loadXFile(XFile file) async {
    if (!mounted) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final bytes = await file.readAsBytes();
      if (mounted) {
        setState(() {
          _bytes = bytes;
          _loading = false;
        });
      }
    } catch (e) {
      if (mounted)
        setState(() {
          _error = e.toString();
          _loading = false;
        });
    }
  }

  Future<void> _loadLocalPath(String path) async {
    if (!mounted) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      if (kIsWeb) {
        // Web: 路径无法直接用 File，尝试作为资源加载
        // 如果是 base64 data URL
        if (path.startsWith('data:')) {
          final base64 = path.split(',').last;
          _bytes = Uint8List.fromList(base64Decode(base64));
          if (mounted)
            setState(() {
              _loading = false;
            });
          return;
        }
        // Web 无法从路径加载本地文件
        if (mounted)
          setState(() {
            _loading = false;
            _error = 'web_no_path';
          });
      } else {
        // Mobile/Desktop
        final file = File(path);
        if (await file.exists()) {
          _bytes = await file.readAsBytes();
          if (mounted)
            setState(() {
              _loading = false;
            });
        } else {
          if (mounted)
            setState(() {
              _loading = false;
              _error = 'file_not_found';
            });
        }
      }
    } catch (e) {
      if (mounted)
        setState(() {
          _error = e.toString();
          _loading = false;
        });
    }
  }

  @override
  Widget build(BuildContext context) {
    // 1. 网络 URL
    if (widget.networkUrl != null && widget.networkUrl!.isNotEmpty) {
      // Web：默认 NetworkImage 走 fetch，跨端口常触发 CORS；用 HTML <img> 可正常显示本机后端 /uploads
      return Image.network(
        widget.networkUrl!,
        width: widget.width,
        height: widget.height,
        fit: widget.fit,
        webHtmlElementStrategy: kIsWeb
            ? WebHtmlElementStrategy.prefer
            : WebHtmlElementStrategy.never,
        loadingBuilder: (_, child, progress) {
          if (progress == null) return child;
          return _buildLoading();
        },
        errorBuilder: (_, __, ___) => _buildErrorOrFallback(),
      );
    }

    // 2. 内存 bytes（从本地 XFile/File 加载）
    if (_bytes != null) {
      return Image.memory(
        _bytes!,
        width: widget.width,
        height: widget.height,
        fit: widget.fit,
        errorBuilder: (_, __, ___) => _buildErrorOrFallback(),
      );
    }

    // 3. 加载中
    if (_loading) return _buildLoading();

    // 4. 错误或占位
    return _buildErrorOrFallback();
  }

  Widget _buildLoading() {
    return Container(
      width: widget.width,
      height: widget.height,
      color: Colors.grey.shade100,
      child: const Center(child: CircularProgressIndicator(strokeWidth: 2)),
    );
  }

  Widget _buildErrorOrFallback() {
    if (widget.errorWidget != null) return widget.errorWidget!;
    if (widget.placeholder != null) return widget.placeholder!;
    return Container(
      width: widget.width,
      height: widget.height,
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Colors.grey.shade100, Colors.grey.shade200],
        ),
      ),
      child: const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.image_not_supported_outlined,
                color: Colors.grey, size: 34),
            SizedBox(height: 6),
            Text(
              '图片加载失败',
              style: TextStyle(fontSize: 12, color: Colors.grey),
            ),
          ],
        ),
      ),
    );
  }
}
