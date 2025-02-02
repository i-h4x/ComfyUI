import torch

from nodes import MAX_RESOLUTION

class LatentCompositeMasked:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "destination": ("LATENT",),
                "source": ("LATENT",),
                "x": ("INT", {"default": 0, "min": 0, "max": MAX_RESOLUTION, "step": 8}),
                "y": ("INT", {"default": 0, "min": 0, "max": MAX_RESOLUTION, "step": 8}),
            },
            "optional": {
                "mask": ("MASK",),
            }
        }
    RETURN_TYPES = ("LATENT",)
    FUNCTION = "composite"

    CATEGORY = "latent"

    def composite(self, destination, source, x, y, mask = None):
        output = destination.copy()
        destination = destination["samples"].clone()
        source = source["samples"]

        x = max(-source.shape[3] * 8, min(x, destination.shape[3] * 8))
        y = max(-source.shape[2] * 8, min(y, destination.shape[2] * 8))

        left, top = (x // 8, y // 8)
        right, bottom = (left + source.shape[3], top + source.shape[2],)


        if mask is None:
            mask = torch.ones_like(source)
        else:
            mask = mask.clone()
            mask = torch.nn.functional.interpolate(mask[None, None], size=(source.shape[2], source.shape[3]), mode="bilinear")
            mask = mask.repeat((source.shape[0], source.shape[1], 1, 1))

        # calculate the bounds of the source that will be overlapping the destination
        # this prevents the source trying to overwrite latent pixels that are out of bounds
        # of the destination
        visible_width, visible_height = (destination.shape[3] - left + min(0, x), destination.shape[2] - top + min(0, y),)

        mask = mask[:, :, :visible_height, :visible_width]
        inverse_mask = torch.ones_like(mask) - mask

        source_portion = mask * source[:, :, :visible_height, :visible_width]
        destination_portion = inverse_mask  * destination[:, :, top:bottom, left:right]

        destination[:, :, top:bottom, left:right] = source_portion + destination_portion

        output["samples"] = destination

        return (output,)

class MaskToImage:
    @classmethod
    def INPUT_TYPES(s):
        return {
                "required": {
                    "mask": ("MASK",),
                }
        }

    CATEGORY = "mask"

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "mask_to_image"

    def mask_to_image(self, mask):
        result = mask[None, :, :, None].expand(-1, -1, -1, 3)
        return (result,)

class ImageToMask:
    @classmethod
    def INPUT_TYPES(s):
        return {
                "required": {
                    "image": ("IMAGE",),
                    "channel": (["red", "green", "blue"],),
                }
        }

    CATEGORY = "mask"

    RETURN_TYPES = ("MASK",)
    FUNCTION = "image_to_mask"

    def image_to_mask(self, image, channel):
        channels = ["red", "green", "blue"]
        mask = image[0, :, :, channels.index(channel)]
        return (mask,)

class SolidMask:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "value": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "width": ("INT", {"default": 512, "min": 1, "max": MAX_RESOLUTION, "step": 1}),
                "height": ("INT", {"default": 512, "min": 1, "max": MAX_RESOLUTION, "step": 1}),
            }
        }

    CATEGORY = "mask"

    RETURN_TYPES = ("MASK",)

    FUNCTION = "solid"

    def solid(self, value, width, height):
        out = torch.full((height, width), value, dtype=torch.float32, device="cpu")
        return (out,)

class InvertMask:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mask": ("MASK",),
            }
        }

    CATEGORY = "mask"

    RETURN_TYPES = ("MASK",)

    FUNCTION = "invert"

    def invert(self, mask):
        out = 1.0 - mask
        return (out,)

class CropMask:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mask": ("MASK",),
                "x": ("INT", {"default": 0, "min": 0, "max": MAX_RESOLUTION, "step": 1}),
                "y": ("INT", {"default": 0, "min": 0, "max": MAX_RESOLUTION, "step": 1}),
                "width": ("INT", {"default": 512, "min": 1, "max": MAX_RESOLUTION, "step": 1}),
                "height": ("INT", {"default": 512, "min": 1, "max": MAX_RESOLUTION, "step": 1}),
            }
        }

    CATEGORY = "mask"

    RETURN_TYPES = ("MASK",)

    FUNCTION = "crop"

    def crop(self, mask, x, y, width, height):
        out = mask[y:y + height, x:x + width]
        return (out,)

class MaskComposite:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "destination": ("MASK",),
                "source": ("MASK",),
                "x": ("INT", {"default": 0, "min": 0, "max": MAX_RESOLUTION, "step": 1}),
                "y": ("INT", {"default": 0, "min": 0, "max": MAX_RESOLUTION, "step": 1}),
                "operation": (["multiply", "add", "subtract"],),
            }
        }

    CATEGORY = "mask"

    RETURN_TYPES = ("MASK",)

    FUNCTION = "combine"

    def combine(self, destination, source, x, y, operation):
        output = destination.clone()

        left, top = (x, y,)
        right, bottom = (min(left + source.shape[1], destination.shape[1]), min(top + source.shape[0], destination.shape[0]))
        visible_width, visible_height = (right - left, bottom - top,)

        source_portion = source[:visible_height, :visible_width]
        destination_portion = destination[top:bottom, left:right]

        match operation:
            case "multiply":
                output[top:bottom, left:right] = destination_portion * source_portion
            case "add":
                output[top:bottom, left:right] = destination_portion + source_portion
            case "subtract":
                output[top:bottom, left:right] = destination_portion - source_portion

        output = torch.clamp(output, 0.0, 1.0)

        return (output,)

class FeatherMask:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mask": ("MASK",),
                "left": ("INT", {"default": 0, "min": 0, "max": MAX_RESOLUTION, "step": 1}),
                "top": ("INT", {"default": 0, "min": 0, "max": MAX_RESOLUTION, "step": 1}),
                "right": ("INT", {"default": 0, "min": 0, "max": MAX_RESOLUTION, "step": 1}),
                "bottom": ("INT", {"default": 0, "min": 0, "max": MAX_RESOLUTION, "step": 1}),
            }
        }

    CATEGORY = "mask"

    RETURN_TYPES = ("MASK",)

    FUNCTION = "feather"

    def feather(self, mask, left, top, right, bottom):
        output = mask.clone()

        left = min(left, output.shape[1])
        right = min(right, output.shape[1])
        top = min(top, output.shape[0])
        bottom = min(bottom, output.shape[0])

        for x in range(left):
            feather_rate = (x + 1.0) / left
            output[:, x] *= feather_rate

        for x in range(right):
            feather_rate = (x + 1) / right
            output[:, -x] *= feather_rate

        for y in range(top):
            feather_rate = (y + 1) / top
            output[y, :] *= feather_rate

        for y in range(bottom):
            feather_rate = (y + 1) / bottom
            output[-y, :] *= feather_rate

        return (output,)



NODE_CLASS_MAPPINGS = {
    "LatentCompositeMasked": LatentCompositeMasked,
    "MaskToImage": MaskToImage,
    "ImageToMask": ImageToMask,
    "SolidMask": SolidMask,
    "InvertMask": InvertMask,
    "CropMask": CropMask,
    "MaskComposite": MaskComposite,
    "FeatherMask": FeatherMask,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "ImageToMask": "Convert Image to Mask",
    "MaskToImage": "Convert Mask to Image",
}
