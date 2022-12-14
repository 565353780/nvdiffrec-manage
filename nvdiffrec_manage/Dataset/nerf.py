#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json

import torch
import numpy as np

from render import util

from dataset.dataset import Dataset


def _load_img(path):
    img = util.load_image_raw(path)

    if img.dtype != np.float32:  # LDR image
        img = torch.tensor(img / 255, dtype=torch.float32)
        img[..., 0:3] = util.srgb_to_rgb(img[..., 0:3])
    else:
        img = torch.tensor(img, dtype=torch.float32)
    return img


class DatasetNERF(Dataset):

    def __init__(self, cfg_path, FLAGS, examples=None):
        self.FLAGS = FLAGS
        self.examples = examples
        self.base_dir = os.path.dirname(cfg_path)

        # Load config / transforms
        self.cfg = json.load(open(cfg_path, 'r'))

        valid_frame_dict_list = []
        for frame_dict in self.cfg['frames']:
            frame_file_path = frame_dict['file_path']
            if not os.path.exists(os.path.join(self.base_dir, frame_file_path)):
                continue
            valid_frame_dict_list.append(frame_dict)
        self.cfg['frames'] = valid_frame_dict_list

        self.n_images = len(self.cfg['frames'])

        # Determine resolution & aspect ratio
        self.resolution = _load_img(
            os.path.join(self.base_dir,
                         self.cfg['frames'][0]['file_path'])).shape[0:2]
        self.aspect = self.resolution[1] / self.resolution[0]

        print("DatasetNERF: %d images with shape [%d, %d]" %
              (self.n_images, self.resolution[0], self.resolution[1]))

        # Pre-load from disc to avoid slow png parsing
        self.preloaded_data = []
        for i in range(self.n_images):
            self.preloaded_data += [self._parse_frame(self.cfg, i)]
        return

    def _parse_frame(self, cfg, idx):
        # Config projection matrix (static, so could be precomputed)
        fovy = util.fovx_to_fovy(cfg['camera_angle_x'], self.aspect)
        proj = util.perspective(fovy, self.aspect, self.FLAGS.cam_near_far[0],
                                self.FLAGS.cam_near_far[1])

        # Load image data and modelview matrix
        img = _load_img(
            os.path.join(self.base_dir, cfg['frames'][idx]['file_path']))
        mv = torch.linalg.inv(
            torch.tensor(cfg['frames'][idx]['transform_matrix'],
                         dtype=torch.float32))
        campos = torch.linalg.inv(mv)[:3, 3]
        mvp = proj @ mv

        return img[None,
                   ...], mv[None,
                            ...], mvp[None,
                                      ...], campos[None,
                                                   ...]  # Add batch dimension

    def __len__(self):
        return self.n_images if self.examples is None else self.examples

    def __getitem__(self, itr):
        iter_res = self.FLAGS.train_res

        img = []

        img, mv, mvp, campos = self.preloaded_data[itr % self.n_images]

        return {
            'mv': mv,
            'mvp': mvp,
            'campos': campos,
            'resolution': iter_res,
            'spp': self.FLAGS.spp,
            'img': img
        }
