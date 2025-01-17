import torch
import torch.nn as nn
from .util import *
from .loss import *

class conv_bn_relu(nn.Module):
    def __init__(self, in_channels, channels, bn=True):
        super(conv_bn_relu, self).__init__()
        self.BN_ = bn
        self.conv = nn.Conv2d(in_channels, channels, 3, padding=1)
        if self.BN_:
          self.bn = nn.BatchNorm2d(channels)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x):
        x = self.conv(x)
        if self.BN_:
          x = self.bn(x)
        x = self.relu(x)
        return x

class cnn_module(nn.Module):
    def __init__(self, out_channel=15):
        super(cnn_module, self).__init__()
        self.conv1 = conv_bn_relu(5, 64)
        self.conv2 = conv_bn_relu(64, 64)
        self.pool1 = nn.MaxPool2d(3, 2, 1)

        self.conv3 = conv_bn_relu(64, 64)
        self.conv4 = conv_bn_relu(64, 64)
        self.pool2 = nn.MaxPool2d(3, 2, 1)

        self.conv5 = conv_bn_relu(64, 64)
        self.conv6 = conv_bn_relu(64, 64)

        self.conv6_up = nn.Upsample(scale_factor=4)
        self.conv4_up = nn.Upsample(scale_factor=2)

        self.conv7 = conv_bn_relu(197, out_channel, False)

    def forward(self, x):

        conv1 = self.conv1(x)
        conv2 = self.conv2(conv1)
        pool1 = self.pool1(conv2)

        conv3 = self.conv3(pool1)
        conv4 = self.conv4(conv3)
        pool2 = self.pool2(conv4)

        conv5 = self.conv5(pool2)
        conv6 = self.conv6(conv5)

        conv6_up = self.conv6_up(conv6)
        conv4_up = self.conv4_up(conv4)
        # print("concat x, 2, 4_up, 6_up ", x.shape, conv2.shape, conv4_up.shape, conv6_up.shape)
        conv2, conv4_up, conv6_up = crop_like(conv2, x), crop_like(conv4_up, x), crop_like(conv6_up, x)
        conv_concat = torch.cat((x, conv2, conv4_up, conv6_up), 1)

        conv7 = self.conv7(conv_concat)
        conv7 = crop_like(conv7, x)
        conv_comb = torch.cat((x, conv7), 1)

        return conv_comb


def crop_like(x, target):
    if x.size()[2:] == target.size()[2:]:
        return x
    else:
        return x[:, :, :target.size(2), :target.size(3)]

class SuperPixelSamplingNet(nn.Module):
    def __init__(self, num_spixels, num_iter, num_spixels_h, num_spixels_w, device, dtype='train', ssn=0):
        super(SuperPixelSamplingNet, self).__init__()
        if ssn:
            self.trans_features = cnn_module()
        else:
            self.trans_features = None
        self.num_spixels = num_spixels
        self.num_iter = num_iter
        self.num_spixels_h = num_spixels_h
        self.num_spixels_w = num_spixels_w
        self.num_spixels = num_spixels_h * num_spixels_w
        self.dtype = dtype
        self.ssn = ssn
        self.device = device

    def count_parameters(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)

    def forward(self, x, args):
        
        spixel_h, spixel_w, init_index, cir_index, p2sp_index, invisible, problabel = args

        if self.ssn:
            trans_features = self.trans_features(x)
        else:
            trans_features = x
        self.num_spixels_h = spixel_h[0]
        self.num_spixels_w = spixel_w[0]
        self.num_spixels = spixel_h[0] * spixel_w[0]


        # init spixel feature
        spixel_feature = SpixelFeature(trans_features, init_index, max_spixels=self.num_spixels)

        for i in range(self.num_iter):
            spixel_feature, _ = exec_iter(spixel_feature, trans_features, cir_index, p2sp_index,
                                                              invisible, self.num_spixels_h, self.num_spixels_w, self.device)

        final_pixel_assoc = compute_assignments(spixel_feature, trans_features, p2sp_index, invisible, self.device)  # out of memory
        if self.dtype == 'layer':
            new_spixel_feat = SpixelFeature2(x, final_pixel_assoc, cir_index, invisible,
                                             self.num_spixels_h, self.num_spixels_w)
            new_spix_indices = compute_final_spixel_labels(final_pixel_assoc, p2sp_index,
                                                           self.num_spixels_h, self.num_spixels_w)
            recon_feat2 = Semar(new_spixel_feat, new_spix_indices)
            return recon_feat2, new_spix_indices


        elif self.dtype == 'train':
            new_spixel_feat = SpixelFeature2(x, final_pixel_assoc, cir_index, invisible,
                                             self.num_spixels_h, self.num_spixels_w)
            new_spix_indices = compute_final_spixel_labels(final_pixel_assoc, p2sp_index,
                                                           self.num_spixels_h, self.num_spixels_w)
            recon_feat2 = Semar(new_spixel_feat, new_spix_indices)


            # requires problabels
            spixel_label = SpixelFeature2(problabel, final_pixel_assoc, cir_index, invisible,
                                          self.num_spixels_h, self.num_spixels_w)
            recon_label = decode_features(final_pixel_assoc, spixel_label, p2sp_index,
                                          self.num_spixels_h, self.num_spixels_w, self.num_spixels, 50)
            return recon_feat2, recon_label

        elif self.dtype == 'test':
            new_spixel_feat = SpixelFeature2(x, final_pixel_assoc, cir_index, invisible,
                                             self.num_spixels_h, self.num_spixels_w)
            new_spix_indices = compute_final_spixel_labels(final_pixel_assoc, p2sp_index,
                                                           self.num_spixels_h, self.num_spixels_w)
            recon_feat2 = Semar(new_spixel_feat, new_spix_indices)
            
            
            # requires problabels
            spixel_label = SpixelFeature2(problabel, final_pixel_assoc, cir_index, invisible,
                                          self.num_spixels_h, self.num_spixels_w)
            recon_label = decode_features(final_pixel_assoc, spixel_label, p2sp_index,
                                          self.num_spixels_h, self.num_spixels_w, self.num_spixels, 50)
            # import pdb
            # pdb.set_trace()
            return recon_feat2, recon_label, new_spix_indices

        else:
            print("Not doing segmentation")
            pass

class Loss(nn.Module):
    def __init__(self):
        super(Loss, self).__init__()
        self.loss1 = position_color_loss()
        self.loss2 = LossWithoutSoftmax()

    def forward(self, recon_feat2, pixel_feature, recon_label, label):
        loss1 = self.loss1(recon_feat2, pixel_feature)
        loss2 = self.loss2(recon_label, label)

        return loss1 + loss2, loss1, loss2


def SSN(pretrained, spixel_size, num_steps=10, dtype = 'layer', device = 'cuda'):    
    num_spixel_h, num_spixel_w = spixel_size
    num_spixels = num_spixel_h * num_spixel_w
    model = SuperPixelSamplingNet(num_spixels=num_spixels, num_iter=num_steps, num_spixels_h=num_spixel_h, num_spixels_w=num_spixel_w, device=device, dtype=dtype, ssn=bool(pretrained))
    print(f"SSNLayer size: {model.count_parameters()}")
    model = torch.nn.DataParallel(model)
    if pretrained:
        if torch.cuda.is_available():
            model.load_state_dict(torch.load(pretrained))
        else:
            model.load_state_dict(torch.load(pretrained, map_location='cpu'))
    else:
        print('no model')
    return model

def superpixel_flow( flow, spix_indices):
    B, _, H, W  = spix_indices.size()
    spix_indices = spix_indices.reshape(B,1, -1)
    flow = flow.reshape(B,2, -1)

    for b in range(flow.size(0)):
        for Ci in range(len(torch.unique(spix_indices))):
            Ci_ROI = spix_indices == Ci
            flowCi_patchx, flowCi_patchy = flow[b, :1][Ci_ROI[b]], flow[b, 1:][Ci_ROI[b]] 
            meanx, meany = torch.median(flowCi_patchx), torch.median(flowCi_patchy)
            # print(meanx.item(), meany.item())
            flow[b, :1][Ci_ROI[b]] = meanx
            flow[b, 1:][Ci_ROI[b]] = meany

    segmentedflow = flow.reshape(B, 2, H, W)
    return segmentedflow, spix_indices