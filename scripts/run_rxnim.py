#!/usr/bin/env python
"""Run RxnIM-7B on all 200 contest images. Save raw responses + parsed JSON.

Usage:
  python scripts/run_rxnim.py <model_path> <img_dir> <out_dir>

Defaults: model = external/datasets/RxnIM/ReactionImgLLM-7b,
          img = img/, out = rxnim_out_raw/
"""
import sys, os, json, pathlib, time
from PIL import Image
import torch

# Repo path setup
REPO = pathlib.Path(__file__).parent.parent / "external" / "datasets" / "RxnIM-repo"
sys.path.insert(0, str(REPO))

# Imports from the RxnIM/Shikra repo
from mmengine import Config
import transformers
from mllm.dataset.process_function import PlainBoxFormatter
from mllm.dataset.builder import prepare_interactive
from mllm.models.builder.build_shikra import load_pretrained_shikra

# Prompt for reaction extraction (Task_1 from webdemo_re.py)
PROMPT = (
    "Please list every reaction in this image <image> in detail. For each "
    "reaction, include the category and unique ID of each object, along with "
    "their coordinates [x1, y1, x2, y2]. Categories include Structure (<Str>) "
    "and Text (<Txt>). Describe their roles in each reaction(<Rxn/st> to "
    "<Rxn/ed>), including Reactants (<Rct/st> to <Rct/ed>), Conditions "
    "(<Cnd/st> to <Cnd/ed>), and Products (<Prd/st> to <Prd/ed>). Note that "
    "Reactants and Products must include at least one object, while Conditions "
    "can be specified without any objects. Each reaction should be listed in "
    "the following structured output format: <Rxn/st><Rct/st>(object 1)..."
    "<Rct/ed><Cnd/st>(object 2)...<Cnd/ed><Prd/st>(object 3)...<Prd/ed><Rxn/ed>"
    ",<Rxn/st>.... Only the Conditions section can be empty(<Cnd/st><Cnd/ed> "
    "without anything between)."
)

def main():
    model_path = sys.argv[1] if len(sys.argv) > 1 else \
        "external/datasets/RxnIM/ReactionImgLLM-7b"
    img_dir = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else "img")
    out_dir = pathlib.Path(sys.argv[3] if len(sys.argv) > 3 else "rxnim_out_raw")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading RxnIM-7B from {model_path}...")
    model_args = Config(dict(
        type='shikra', version='v1', cache_dir=None,
        model_name_or_path=model_path,
        vision_tower=r'openai/clip-vit-large-patch14',
        pretrain_mm_mlp_adapter=None,
        mm_vision_select_layer=-2, model_max_length=3072,
        freeze_backbone=False, tune_mm_mlp_adapter=False, freeze_mm_mlp_adapter=False,
        is_multimodal=True, sep_image_conv_front=False,
        image_token_len=256, mm_use_im_start_end=True,
        target_processor=dict(boxes=dict(type='PlainBoxFormatter')),
        process_func_args=dict(
            conv=dict(type='ShikraConvProcess'),
            target=dict(type='BoxFormatProcess'),
            text=dict(type='ShikraTextProcess'),
            image=dict(type='ShikraImageProcessor'),
        ),
        conv_args=dict(
            conv_template='vicuna_v1.1',
            transforms=dict(type='Expand2square'),
            tokenize_kwargs=dict(truncation_size=None),
        ),
        gen_kwargs_set_pad_token_id=True,
        gen_kwargs_set_bos_token_id=True,
        gen_kwargs_set_eos_token_id=True,
    ))
    training_args = Config(dict(bf16=False, fp16=True, device='cuda', fsdp=None))

    t0 = time.time()
    model, preprocessor = load_pretrained_shikra(model_args, training_args, torch_dtype=torch.float16)
    model.half()
    if not getattr(model, 'hf_device_map', None):
        model.to(training_args.device)
    print(f"Model loaded in {time.time()-t0:.1f}s")
    preprocessor['target'] = {'boxes': PlainBoxFormatter()}
    tokenizer = preprocessor['text']

    img_paths = sorted(img_dir.glob("*.png"))
    print(f"Processing {len(img_paths)} images...")

    overall_t0 = time.time()
    for i, p in enumerate(img_paths):
        out_path = out_dir / f"{p.stem}.txt"
        if out_path.exists():
            continue
        try:
            image = Image.open(p).convert("RGB")
            # Build interactive session
            ds = prepare_interactive(model_args, preprocessor)
            ds.set_image(image)
            ds.append_message(role=ds.roles[0], message=PROMPT)
            model_inputs = ds.to_model_input()
            model_inputs['images'] = model_inputs['images'].to(torch.float16)

            gen_kwargs = dict(
                use_cache=True, do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
                bos_token_id=tokenizer.bos_token_id,
                eos_token_id=tokenizer.eos_token_id,
                max_new_tokens=1024,
            )
            input_ids = model_inputs['input_ids']
            with torch.inference_mode(), torch.autocast(dtype=torch.float16, device_type='cuda'):
                output_ids = model.generate(**model_inputs, **gen_kwargs)
            response = tokenizer.batch_decode(
                output_ids[:, input_ids.shape[-1]:], skip_special_tokens=True
            )[0]

            out_path.write_text(response, encoding="utf-8")
            elapsed = time.time() - overall_t0
            print(f"[{i+1}/{len(img_paths)}] {p.name}: {len(response)} chars  ({elapsed:.1f}s)")
        except Exception as e:
            print(f"[{i+1}/{len(img_paths)}] {p.name}: FAILED - {e}")
            import traceback; traceback.print_exc()
            continue

    print(f"Done in {time.time()-overall_t0:.1f}s")

if __name__ == "__main__":
    main()
