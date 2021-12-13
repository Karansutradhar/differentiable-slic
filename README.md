# Differentiable-slic
This project is a study on differentiable-slic, which uses superpixel sampling networks to obtain segmented optical flow

## Motion Segmentation Task 

We will be using [Davis Dataset](https://graphics.ethz.ch/Downloads/Data/Davis/DAVIS-data.zip) for motion segmentation.

`pytorch_ssn` package has the differentiable slic + optical flow functions. 

The optical flow we use here is using a method called `RAFT`

We already finetuned the optical flow model with the simulated data from [here](https://drive.google.com/drive/folders/16V2-7NOEKJjsb3ChHGXy3AGudNjWGqA-?usp=sharing)

Even though we want to train the model end to end, due to resource and time constraints, we will choose to pre generate the superpixels and optical flow from the corresponding networks. `slicgenerator.py` generates the SuperpixelSamplingNetwork's conv-features and saves them. This network is fairly generalizable, hence it was not finetuned.  `flowgenerator.py` generates optical flow and saves them. Load these two, along with images and groundtruth in the dataloader `DavisMoSegLoader` 
and train the UNet network. Refer `train_unet.py` for the train and validation functions.


[TODO]  : Follow the same routine, but train the U-Net for [multi-object video segmentation using Davis Dataset](https://davischallenge.org/davis2017/code.html#unsupervised) 

Additionally
Differentiable slic
Refer the depthEstimation.ipynb notebook for step by step implementation details to obtain optical flow and compute depth using airsim data which is present [here](https://drive.google.com/drive/folders/16V2-7NOEKJjsb3ChHGXy3AGudNjWGqA-?usp=sharing) 

# Reference Material:
1. Superpixel Segmentation with Fully Convolutional Networks : https://arxiv.org/pdf/2003.12929.pdf

2. Superpixel Sampling Networks : https://arxiv.org/pdf/1807.10174.pdf

3. AN IMAGE IS WORTH 16X16 WORDS: TRANSFORMERS FOR IMAGE RECOGNITION AT SCALE. https://arxiv.org/pdf/2010.11929.pdf

4. Datasets: https://theairlab.org/tartanair-dataset/

